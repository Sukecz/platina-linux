// SPDX-License-Identifier: GPL-2.0-only
#include "platina_exposure.h"
#include <cassert>
#include <limits>

int main()
{
    // Microseconds must become sensor lines, with rounding and mode limits.
    assert(platina::exposureLines(10000, 12.5, 4, 2000) == 800);
    assert(platina::exposureLines(100, 30, 4, 2000) == 4);
    assert(platina::exposureLines(100000, 12.5, 4, 2000) == 2000);
    assert(platina::exposureLines(100, 12, 4, 2000) == 8);
    assert(platina::exposureLines(102, 12, 4, 2000) == 9);
    assert(platina::exposureLines(std::numeric_limits<int32_t>::max(), .01, 1, 65535) == 65535);
    assert(platina::sensorGain(8, 1, 4) == 4);
    assert(platina::sensorGain(.5, 1, 8) == 1);
    assert(platina::sensorGain(2.5, 1, 8) == 2.5);
    assert(platina::sensorGain(std::numeric_limits<double>::quiet_NaN(), 1, 8) == 1);
    assert(platina::sensorGain(std::numeric_limits<double>::infinity(), 1, 8) == 1);

    // Frame snapshots preserve their own manual request when later frames change.
    platina::ExposureSettings settings;
    assert(settings.automatic);
    settings = {false, 25000, 2.5};
    const auto frame = settings;
    settings = {true, 5000, 1};
    assert(!frame.automatic && frame.exposureUs == 25000 && frame.gain == 2.5);
}
