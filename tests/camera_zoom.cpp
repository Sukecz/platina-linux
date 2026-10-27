// SPDX-License-Identifier: GPL-2.0-only
#include "platina_zoom.h"
#include <cassert>
#include <sstream>
#include <string>

int main()
{
    const std::string old = "1.1 1 1.14 1 1.89 1.61 90 1.5 40 30 0 25000 2.5";
    for (auto value : {"1", "1.5", "2", "2.5", "4", "8", "10"}) {
        std::istringstream stream(old + " " + value);
        assert(platina::zoomFromControls(stream) == std::stof(value));
    }
    for (auto value : {"", "0", "0.99", "10.01", "nan", "inf", "broken"}) {
        std::istringstream stream(old + " " + value);
        assert(platina::zoomFromControls(stream) == 1);
    }
    std::istringstream truncated("1 1 1 1");
    assert(platina::zoomFromControls(truncated) == 1);
    for (float zoom : {1.0f, 1.5f, 2.0f, 4.0f, 8.0f, 10.0f}) {
        float low = platina::zoomCoordinate(0, zoom);
        float high = platina::zoomCoordinate(1, zoom);
        assert(low >= 0 && high <= 1);
        assert(std::abs((high - low) - 1 / zoom) < 0.000001f);
        assert(platina::zoomCoordinate(.5f, zoom) == .5f);
        for (float x : {0.0f, .25f, .5f, 1.0f}) {
            // All quarter-turn coordinate transforms use only x/y and 1-x/y.
            assert(std::abs(platina::zoomCoordinate(1-x, zoom) -
                            (1-platina::zoomCoordinate(x, zoom))) < 0.000001f);
        }
        for (unsigned scale : {1U, 2U, 3U, 4U, 6U}) {
            const unsigned w = (4024U / scale) & ~3U, h = (3016U / scale) & ~3U;
            const auto crop = platina::centerCrop(w, h, zoom);
            assert(crop.x * 2 + crop.width == w && crop.y * 2 + crop.height == h);
            assert(crop.width % 4 == 0 && crop.height % 4 == 0);
            assert(crop.x + crop.width <= w && crop.y + crop.height <= h);
            assert(std::abs(double(crop.width) / w - 1 / zoom) < 4.0 / w);
            if (zoom == 1) assert(crop.x == 0 && crop.y == 0 && crop.width == w && crop.height == h);
        }
    }
}
