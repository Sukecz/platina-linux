/* SPDX-License-Identifier: LGPL-2.1-or-later */
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace platina {

struct ExposureSettings {
	bool automatic = true;
	int32_t exposureUs = 10000;
	double gain = 1.0;
};

/* Clamp before conversion to avoid integer overflow on external controls.
 * Sensor exposure uses whole lines; metadata reports the quantized result. */
inline int32_t exposureLines(int32_t exposureUs, double lineUs,
			     int32_t minimum, int32_t maximum)
{
	double lines = std::clamp(exposureUs / lineUs,
				  double(minimum), double(maximum));
	return static_cast<int32_t>(std::lround(lines));
}

inline double sensorGain(double requested, double minimum, double maximum)
{
	return std::isfinite(requested) ? std::clamp(requested, minimum, maximum) : minimum;
}

} /* namespace platina */
