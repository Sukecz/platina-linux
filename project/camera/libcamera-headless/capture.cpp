// SPDX-License-Identifier: GPL-2.0-only
// Headless camera consumer. Bounded ISP requests and one latest JPEG job, no FIFO.
#include <libcamera/camera.h>
#include <libcamera/camera_manager.h>
#include <libcamera/control_ids.h>
#include <libcamera/formats.h>
#include <libcamera/framebuffer_allocator.h>
#include <libcamera/request.h>
#include <cstdio>
#include <jpeglib.h>
#include <libyuv.h>
#include <sys/mman.h>
#include <signal.h>
#include <unistd.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#include "platina_exposure.h"
#include "platina_zoom.h"

using Clock = std::chrono::steady_clock;
static std::atomic<bool> stopping{false};
static_assert(std::atomic<bool>::is_always_lock_free);
static void stop(int) { stopping = true; }
static int64_t monotonicNs() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
}
struct Settings {
    float gamma = 2.2f, contrast = 1.0f, saturation = 1.0f, red = 1.0f, blue = 1.0f;
    float scale = 2.0f;
    int automatic = 1, rotation = 90, quality = 50, fps = 30;
    int exposureAuto = 1, exposureUs = 10000;
    float analogueGain = 1.0f;
    float zoom = 1.0f;
};
class Capture {
public:
    std::shared_ptr<libcamera::Camera> camera;
    libcamera::Stream *stream = nullptr;
    unsigned width = 0, height = 0, stride = 0;
    double ispScale = 1;
    int ispRotation = 0;
    bool ispSaturation = false;
    bool ispZoom = false;
    unsigned inFlight = 0, maxInFlight = 1;
    struct EncoderBuffers { std::vector<uint8_t> scaled, rotated, colored, packed; };
    std::mutex publishMutex;
    int64_t lastPublished = 0;
    Clock::time_point fpsStarted = Clock::now();
    unsigned fpsFrames = 0;
    double recentFps = 0;
    std::string output;
    Settings defaults;
    struct Mapping { void *base; size_t size; uint8_t *pixels; };
    std::map<libcamera::FrameBuffer *, Mapping> maps;
    std::mutex mutex;
    std::condition_variable changed;
    std::deque<libcamera::Request *> ready;
    libcamera::Request *latest = nullptr;
    std::atomic<uint64_t> captured{0}, encoded{0};
    std::vector<std::thread> encoders;
    Clock::time_point started = Clock::now();

    Settings settings() const {
        Settings s = defaults;
        std::ifstream file(output + ".controls");
        Settings candidate;
        if (file >> candidate.gamma >> candidate.contrast >> candidate.saturation >>
            candidate.automatic >> candidate.red >> candidate.blue >> candidate.rotation >>
            candidate.scale >> candidate.quality >> candidate.fps >>
            candidate.exposureAuto >> candidate.exposureUs >> candidate.analogueGain >> candidate.zoom) {
            if (std::isfinite(candidate.gamma) && candidate.gamma >= .5f && candidate.gamma <= 4 &&
                std::isfinite(candidate.contrast) && candidate.contrast >= .5f && candidate.contrast <= 1.8f &&
                std::isfinite(candidate.saturation) && candidate.saturation >= 0 && candidate.saturation <= 2 &&
                std::isfinite(candidate.red) && candidate.red >= .25f && candidate.red <= 4 &&
                std::isfinite(candidate.blue) && candidate.blue >= .25f && candidate.blue <= 4 &&
                (candidate.automatic == 0 || candidate.automatic == 1) &&
                (candidate.rotation == 0 || candidate.rotation == 90 || candidate.rotation == 180 || candidate.rotation == 270) &&
                (candidate.scale == 1 || candidate.scale == 1.5f || candidate.scale == 2 || candidate.scale == 3 || candidate.scale == 4 || candidate.scale == 6) && candidate.quality >= 10 && candidate.quality <= 95 &&
                candidate.fps >= 10 && candidate.fps <= 30 &&
                (candidate.exposureAuto == 0 || candidate.exposureAuto == 1) &&
                candidate.exposureUs >= 100 && candidate.exposureUs <= 100000 &&
                std::isfinite(candidate.analogueGain) && candidate.analogueGain >= 1 && candidate.analogueGain <= 8 &&
                std::isfinite(candidate.zoom) && candidate.zoom >= 1 && candidate.zoom <= 10)
                { candidate.fps = 30; s = candidate; }
        }
        return s;
    }
    void recycle(libcamera::Request *request) {
        request->reuse(libcamera::Request::ReuseBuffers);
        ready.push_back(request);
    }
    void complete(libcamera::Request *request) {
        if (request->status() == libcamera::Request::RequestCancelled || stopping) return;
        auto *buffer = request->findBuffer(stream);
        if (!buffer || buffer->metadata().status != libcamera::FrameMetadata::FrameSuccess) {
            std::cerr << "Camera buffer failed\n"; stopping = true; changed.notify_all(); return;
        }
        captured++;
        {
            std::lock_guard<std::mutex> lock(mutex);
            // Drop an obsolete job before it enters the encoder.
            if (latest) recycle(latest);
            latest = request;
            if (inFlight) --inFlight;
        }
        changed.notify_all();
    }
    bool encode(libcamera::Request *request, EncoderBuffers &storage) {
        auto &scaledPixels = storage.scaled;
        auto &rotatedPixels = storage.rotated;
        auto &coloredPixels = storage.colored;
        const Settings s = settings();
        const int rotation = (s.rotation - ispRotation + 360) % 360;
        const float saturation = ispSaturation ? 1.0f : s.saturation;
        auto *buffer = request->findBuffer(stream);
        const auto &m = maps.at(buffer);
        struct jpeg_compress_struct jpeg{};
        struct jpeg_error_mgr error{};
        jpeg.err = jpeg_std_error(&error);
        jpeg_create_compress(&jpeg);
        unsigned char *data = nullptr;
        unsigned long length = 0;
        jpeg_mem_dest(&jpeg, &data, &length);
        const double scale = std::max(1.0, double(s.scale) / ispScale);
        const unsigned sampleWidth = static_cast<unsigned>(width / scale) & ~3U, sampleHeight = static_cast<unsigned>(height / scale) & ~3U;
        const bool portrait = rotation == 90 || rotation == 270;
        jpeg.image_width = portrait ? sampleHeight : sampleWidth;
        jpeg.image_height = portrait ? sampleWidth : sampleHeight;
        jpeg.input_components = 4;
        jpeg.in_color_space = JCS_EXT_BGRX;
        jpeg_set_defaults(&jpeg);
        jpeg_set_quality(&jpeg, s.quality, TRUE);
        jpeg_start_compress(&jpeg, TRUE);
        const auto sensorTime = request->metadata().get(libcamera::controls::SensorTimestamp).value_or(monotonicNs());
        char marker[80];
        int markerLength = snprintf(marker, sizeof(marker), "platina_capture_ns=%lld", static_cast<long long>(sensorTime));
        jpeg_write_marker(&jpeg, JPEG_COM, reinterpret_cast<const JOCTET *>(marker), markerLength);
        const int64_t encodingStart = monotonicNs();
        const uint8_t *pixels = m.pixels;
        unsigned pixelStride = stride;
        // GPU stride 8192 causes severe cache-set conflicts during transposition.
        // Copy rows once into a tightly packed cached buffer before rotation.
        if (rotation && scale == 1 && stride % 4096 == 0) {
            storage.packed.resize(width * height * 4);
            for (unsigned y = 0; y < height; ++y)
                std::memcpy(storage.packed.data() + y * width * 4,
                            pixels + y * stride, width * 4);
            pixels = storage.packed.data(); pixelStride = width * 4;
        }
        const auto crop = platina::centerCrop(width, height, ispZoom ? 1.0f : s.zoom);
        if (scale > 1 || (!ispZoom && s.zoom > 1)) {
            scaledPixels.resize(sampleWidth * sampleHeight * 4);
            if (libyuv::ARGBScale(pixels + crop.y * pixelStride + crop.x * 4,
                                 pixelStride, crop.width, crop.height,
                                 scaledPixels.data(), sampleWidth * 4,
                                 sampleWidth, sampleHeight,
                                 crop.width < sampleWidth ? libyuv::kFilterBilinear : libyuv::kFilterBox) < 0)
                return false;
            pixels = scaledPixels.data(); pixelStride = sampleWidth * 4;
        }
        if (rotation) {
            rotatedPixels.resize(sampleWidth * sampleHeight * 4);
            if (libyuv::ARGBRotate(pixels, pixelStride, rotatedPixels.data(),
                                  jpeg.image_width * 4, sampleWidth, sampleHeight,
                                  static_cast<libyuv::RotationMode>(rotation)) < 0)
                return false;
            pixels = rotatedPixels.data(); pixelStride = jpeg.image_width * 4;
        }
        const int64_t rotatedAt = monotonicNs();
        if (std::abs(saturation - 1.0f) > .001f) {
            const float sat = saturation, other = 1.0f - sat;
            auto coefficient = [](float value) { return static_cast<int8_t>(std::lround(value * 64)); };
            const int8_t matrix[16] = {
                coefficient(.114f + .886f * sat), coefficient(.587f * other), coefficient(.299f * other), 0,
                coefficient(.114f * other), coefficient(.587f + .413f * sat), coefficient(.299f * other), 0,
                coefficient(.114f * other), coefficient(.587f * other), coefficient(.299f + .701f * sat), 0,
                0, 0, 0, 64
            };
            coloredPixels.resize(sampleWidth * sampleHeight * 4);
            if (libyuv::ARGBColorMatrix(pixels, pixelStride, coloredPixels.data(),
                                       jpeg.image_width * 4, matrix,
                                       jpeg.image_width, jpeg.image_height) < 0) return false;
            pixels = coloredPixels.data(); pixelStride = jpeg.image_width * 4;
        }
        const int64_t compressingAt = monotonicNs();
        while (jpeg.next_scanline < jpeg.image_height) {
            JSAMPROW row = const_cast<uint8_t *>(pixels + jpeg.next_scanline * pixelStride);
            jpeg_write_scanlines(&jpeg, &row, 1);
        }
        jpeg_finish_compress(&jpeg);
        jpeg_destroy_compress(&jpeg);
        const int64_t finished = monotonicNs();
        const auto gains = request->metadata().get(libcamera::controls::ColourGains);
        const auto exposure = request->metadata().get(libcamera::controls::ExposureTime);
        const auto sensorGain = request->metadata().get(libcamera::controls::AnalogueGain);
        // Independent encoders may finish out of order. Publish only newer
        // sensor frames, and serialize the atomic JPEG + metadata replacement.
        std::lock_guard<std::mutex> publish(publishMutex);
        if (sensorTime <= lastPublished) { free(data); return true; }
        std::string temporary = output + ".new";
        FILE *f = fopen(temporary.c_str(), "wb");
        bool ok = f && fwrite(data, 1, length, f) == length;
        if (f && fclose(f) != 0) ok = false;
        if (ok && rename(temporary.c_str(), output.c_str()) != 0) ok = false;
        free(data);
        if (!ok) return false;
        lastPublished = sensorTime;
        const int64_t published = monotonicNs();
        encoded++;
        fpsFrames++;
        double window = std::chrono::duration<double>(Clock::now() - fpsStarted).count();
        if (window >= 1.0) {
            recentFps = fpsFrames / window;
            fpsFrames = 0; fpsStarted = Clock::now();
        }
        std::ofstream meta(output + ".meta.new");
        meta << "{\"captured_ns\":" << sensorTime << ",\"published_ns\":" << published
             << ",\"sensor_age_ms\":" << (published - sensorTime) / 1000000.0
             << ",\"jpeg_ms\":" << (finished - encodingStart) / 1000000.0
             << ",\"rotate_scale_ms\":" << (rotatedAt - encodingStart) / 1000000.0
             << ",\"compression_ms\":" << (finished - compressingAt) / 1000000.0
             << ",\"frames_in\":" << captured.load() << ",\"frames_out\":" << encoded.load()
             << ",\"fps\":" << recentFps
             << ",\"width\":" << (portrait ? sampleHeight : sampleWidth)
             << ",\"height\":" << (portrait ? sampleWidth : sampleHeight)
             << ",\"red_gain\":" << (gains ? (*gains)[0] : 1.0f)
             << ",\"blue_gain\":" << (gains ? (*gains)[1] : 1.0f)
             << ",\"exposure_us_actual\":" << (exposure ? std::to_string(*exposure) : "null")
             << ",\"analogue_gain_actual\":" << (sensorGain ? std::to_string(*sensorGain) : "null") << "}";
        meta.close();
        rename((output + ".meta.new").c_str(), (output + ".meta").c_str());
        return true;
    }
    void encodeLoop() {
        EncoderBuffers storage;
        while (!stopping) {
            libcamera::Request *request = nullptr;
            {
                std::unique_lock<std::mutex> lock(mutex);
                changed.wait_for(lock, std::chrono::milliseconds(50), [&] { return latest || stopping; });
                if (stopping) break;
                if (!latest) continue;
                request = latest; latest = nullptr;
            }
            if (captured > 10 && !encode(request, storage)) { stopping = true; changed.notify_all(); break; }
            {
                std::lock_guard<std::mutex> lock(mutex);
                recycle(request);
            }
            changed.notify_all();
        }
    }
};
int main(int argc, char **argv) {
    if (argc < 2 || argc > 4 || argv[1][0] != '/') {
        std::cerr << "Usage: platina-camera-capture /absolute/path/latest.jpg [0|90|180|270] [1|2|3|4|6]\n"; return 2;
    }
    signal(SIGINT, stop); signal(SIGTERM, stop);
    Capture c;
    c.output = argv[1];
    if (argc >= 3) {
        std::string angle(argv[2]);
        if (angle != "0" && angle != "90" && angle != "180" && angle != "270") return 2;
        c.defaults.rotation = std::stoi(angle);
    }
    if (argc == 4) {
        std::string scale(argv[3]);
        if (scale != "1" && scale != "1.5" && scale != "2" && scale != "3" && scale != "4" && scale != "6") return 2;
        c.defaults.scale = std::stof(scale);
    }
    const Settings configured = c.settings();
    bool gpu = std::getenv("LIBCAMERA_SOFTISP_MODE") && std::string(std::getenv("LIBCAMERA_SOFTISP_MODE")) == "gpu";
    c.ispScale = gpu ? configured.scale : 1;
    c.ispRotation = gpu && c.ispScale > 1 ? configured.rotation : 0;
    c.ispSaturation = gpu;
    c.ispZoom = gpu;
    setenv("PLATINA_GPU_ROTATION", std::to_string(c.ispRotation).c_str(), 1);
    setenv("PLATINA_CAMERA_CONTROLS", (c.output + ".controls").c_str(), 1);
    libcamera::CameraManager manager;
    if (manager.start() < 0 || manager.cameras().size() != 1) { std::cerr << "Expected one camera\n"; return 1; }
    c.camera = manager.cameras().front();
    if (c.camera->acquire() < 0) return 1;
    auto config = c.camera->generateConfiguration({libcamera::StreamRole::Viewfinder});
    if (!config || config->empty()) return 1;
    auto &cfg = config->at(0);
    // Always read the full sensor. Output scaling never changes the field of view.
    c.maxInFlight = gpu ? 2 : 1;
    if (const char *count = std::getenv("PLATINA_CAMERA_IN_FLIGHT")) {
        try { c.maxInFlight = std::clamp(std::stoul(count), 1UL, 2UL); }
        catch (...) { return 2; }
    }
    cfg.size = { static_cast<unsigned>(4024U / c.ispScale) & ~3U, static_cast<unsigned>(3016U / c.ispScale) & ~3U };
    if (c.ispRotation == 90 || c.ispRotation == 270)
        cfg.size = {cfg.size.height, cfg.size.width};
    cfg.pixelFormat = libcamera::formats::XRGB8888;
    unsigned jpegThreads = 4;
    if (const char *count = std::getenv("PLATINA_JPEG_THREADS")) {
        try { jpegThreads = std::clamp(std::stoul(count), 1UL, 4UL); }
        catch (...) { return 2; }
    }
    cfg.bufferCount = jpegThreads + 4;
    if (config->validate() == libcamera::CameraConfiguration::Invalid || c.camera->configure(config.get()) < 0) return 1;
    for (unsigned id : {libcamera::controls::AeEnable.id(), libcamera::controls::ExposureTime.id(),
                       libcamera::controls::AnalogueGain.id()}) {
        if (!c.camera->controls().count(id)) {
            std::cerr << "Camera pipeline lacks exposure controls\n";
            return 1;
        }
    }
    if (cfg.pixelFormat != libcamera::formats::XRGB8888) return 1;
    c.width = cfg.size.width; c.height = cfg.size.height; c.stride = cfg.stride; c.stream = cfg.stream();
    std::cerr << "Configured " << cfg.toString() << " stride=" << cfg.stride << '\n';
    auto allocator = std::make_unique<libcamera::FrameBufferAllocator>(c.camera);
    if (allocator->allocate(c.stream) < 0) return 1;
    std::vector<std::unique_ptr<libcamera::Request>> requests;
    for (const auto &buffer : allocator->buffers(c.stream)) {
        if (buffer->planes().size() != 1) return 1;
        const auto &plane = buffer->planes()[0];
        size_t size = plane.offset + plane.length;
        if (plane.length < c.stride * c.height) return 1;
        void *base = mmap(nullptr, size, PROT_READ, MAP_SHARED, plane.fd.get(), 0);
        if (base == MAP_FAILED) return 1;
        c.maps.emplace(buffer.get(), Capture::Mapping{base, size, static_cast<uint8_t *>(base) + plane.offset});
        auto request = c.camera->createRequest();
        if (!request || request->addBuffer(c.stream, buffer.get()) < 0) return 1;
        c.ready.push_back(request.get()); requests.push_back(std::move(request));
    }
    c.camera->requestCompleted.connect(&c, &Capture::complete);
    if (c.camera->start() < 0) return 1;
    for (unsigned i = 0; i < jpegThreads; ++i)
        c.encoders.emplace_back(&Capture::encodeLoop, &c);
    bool reconfigure = false;
    auto next = Clock::now();
    while (!stopping) {
        libcamera::Request *request = nullptr;
        {
            std::unique_lock<std::mutex> lock(c.mutex);
            c.changed.wait_for(lock, std::chrono::milliseconds(50), [&] { return stopping || (c.inFlight < c.maxInFlight && !c.ready.empty()); });
            if (stopping) break;
            if (c.inFlight < c.maxInFlight && !c.ready.empty()) {
                request = c.ready.front(); c.ready.pop_front(); ++c.inFlight;
            }
        }
        if (!request) continue;
        auto s = c.settings();
        if (gpu && (double(s.scale) != c.ispScale || s.rotation != configured.rotation)) { reconfigure = true; break; }
        auto &ctrl = request->controls();
        ctrl.set(libcamera::controls::AeEnable, bool(s.exposureAuto));
        if (!s.exposureAuto) {
            ctrl.set(libcamera::controls::ExposureTime, s.exposureUs);
            ctrl.set(libcamera::controls::AnalogueGain, s.analogueGain);
        }
        ctrl.set(libcamera::controls::Gamma, s.gamma);
        ctrl.set(libcamera::controls::Contrast, s.contrast);
        // Saturation is applied with SIMD after the ISP; no costly identity CCM.
        ctrl.set(libcamera::controls::AwbEnable, bool(s.automatic));
        const float gains[2] = {s.red, s.blue};
        ctrl.set(libcamera::controls::ColourGains, libcamera::Span<const float, 2>(gains));
        next = std::max(next, Clock::now());
        std::this_thread::sleep_until(next);
        if (c.camera->queueRequest(request) < 0) stopping = true;
        next += std::chrono::microseconds(1000000 / s.fps);
    }
    stopping = true;
    c.camera->stop();
    c.changed.notify_all();
    for (auto &encoder : c.encoders) if (encoder.joinable()) encoder.join();
    c.camera->requestCompleted.disconnect(&c);
    for (auto &[buffer, map] : c.maps) munmap(map.base, map.size);
    requests.clear(); allocator->free(c.stream); allocator.reset();
    c.camera->release(); config.reset(); c.camera.reset(); manager.stop();
    std::cerr << "Stopped after " << c.captured << " camera frames and " << c.encoded << " JPEGs\n";
    if (reconfigure) { execl(argv[0], argv[0], argv[1], nullptr); return 1; }
    return c.encoded > 0 ? 0 : 1;
}
