/* SPDX-License-Identifier: LGPL-2.1-or-later */
#pragma once

#include <algorithm>
#include <cmath>
#include <istream>

namespace platina {

/* The controls file is atomically replaced by the controller. Zoom is appended
 * after the thirteen existing fields, preserving earlier field positions. */
inline float zoomFromControls(std::istream &input)
{
	double field;
	for (unsigned i = 0; i < 13; ++i) {
		if (!(input >> field) || !std::isfinite(field))
			return 1.0f;
	}
	float zoom;
	return input >> zoom && std::isfinite(zoom) && zoom >= 1.0f && zoom <= 10.0f ? zoom : 1.0f;
}

/* Crop texture coordinates, not the viewport: output size stays unchanged.
 * Centered zoom commutes with each supported quarter-turn rotation. */
inline float zoomCoordinate(float coordinate, float zoom)
{
	return 0.5f + (coordinate - 0.5f) / zoom;
}

struct ZoomCrop {
	unsigned x, y, width, height;
};

/* CPU fallback crops debayered ARGB before its existing resize/rotation pass. */
inline ZoomCrop centerCrop(unsigned width, unsigned height, float zoom)
{
	if (zoom <= 1.0f)
		return {0, 0, width, height};
	unsigned w = std::max(4U, static_cast<unsigned>(width / zoom) & ~3U);
	unsigned h = std::max(4U, static_cast<unsigned>(height / zoom) & ~3U);
	return {(width - w) / 2, (height - h) / 2, w, h};
}

} /* namespace platina */
