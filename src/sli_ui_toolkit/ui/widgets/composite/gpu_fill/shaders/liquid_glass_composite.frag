#version 440

// Pass 2 of LiquidGlassFillWidget: vertical half of the separable blur
// (same discrete-Gaussian kernel as liquid_glass_blur.frag, reading pass
// 1's scratch texture) combined with the tint and a cheap "liquid glass"
// light cue -- a soft top-edge glow (light falling on the panel from
// above) plus a thin rim brightening near the panel's own edges
// (fresnel-ish falloff).
//
// This is the whole visual shell of the flyout, not just its fill: the
// border stroke is drawn here too, replacing BaseFlyout's CPU QPainter
// paintEvent (see GlassHUD.paintEvent, which no-ops for this reason). No
// drop shadow: GlassHUD doesn't want one, and it wouldn't work right
// here anyway -- see below.
//
// Outside the rounded content+border, this outputs real alpha=0 instead of
// an opaque resample of the live backdrop (an earlier version of this
// shader sampled srcTex a second time here and painted it back in verbatim
// to *fake* transparency, working around this app's general QRhiWidget
// alpha=1 invariant -- see docs/dev/rendering/render-pass-contract.md --
// which was written against the *main canvas* pass and Windows/D3D's
// "translucent CSD shell + alpha<1 QRhiWidget clear = desktop hole"
// failure mode, see qrhi-gotchas.md). That resample trick was itself the
// source of a whole family of bugs (Y-flip, stretch, sub-pixel-position
// popping at the crop boundary -- see git history) since it required a
// pixel-perfect reproduction of "whatever is really behind this panel,
// right now" via UV math alone, on a *foreign* widget's texture, with none
// of the layering (other flyouts, tooltips) that real transparency gets
// for free. Real alpha instead lets Qt's own normal compositing show
// whatever is actually behind this widget -- canvas, another flyout,
// tooltip -- correctly, the same way any other translucent Qt widget
// works. Confirmed live-testable on this project's Linux/OpenGL config
// (qrhi-gotchas.md notes "Linux OpenGL/Vulkan usually fine" for the
// translucent-QRhiWidget class of issue); the Windows/D3D failure mode
// this app's general invariant guards against has NOT been re-validated
// for this specific widget on that platform -- test there before shipping
// if that combination matters.

layout(std140, binding = 0) uniform UBuf
{
    vec2 direction;
    float radiusPx;
    float cornerRadiusPx;
    vec4 tint;
    vec2 uvOffset;
    vec2 uvScale;
    vec2 panelSizePx;
    float borderWidthPx;
    float _pad0;
    vec4 borderColor;
    // Debug-only visualization switch (see liquid_glass_widget.py's
    // SLI_LIQUID_GLASS_DEBUG_VIZ env var): 0 = normal render, >0.5 = replace
    // output with a false-color view of the mask math (see bottom of
    // main()), to diagnose the intermittent rounded-corner artifact without
    // guessing blind from the formulas.
    float debugViz;
    vec3 _pad1;
};

layout(binding = 1) uniform sampler2D scratchTex;

layout(location = 0) in vec2 vUv;
layout(location = 0) out vec4 fragColor;

const int TAPS = 8; // -8..8 inclusive => 17 samples, same kernel as pass 1

// Signed distance from a point to a rounded-rect boundary, centered at the
// origin, in pixel units (standard "box minus corner circle" SDF).
float roundedRectSD(vec2 pointPx, vec2 halfSizePx, float radiusPx)
{
    vec2 q = abs(pointPx) - halfSizePx + radiusPx;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radiusPx;
}

void main()
{
    vec2 texel = direction / vec2(textureSize(scratchTex, 0));
    float sigma = max(radiusPx / 3.0, 0.6);

    vec4 sum = vec4(0.0);
    float weightSum = 0.0;
    for (int i = -TAPS; i <= TAPS; i++)
    {
        float fi = float(i);
        float w = exp(-(fi * fi) / (2.0 * sigma * sigma));
        sum += texture(scratchTex, vUv + texel * fi) * w;
        weightSum += w;
    }
    vec4 blurred = sum / max(weightSum, 1e-5);
    vec3 tintedGlass = mix(blurred.rgb, tint.rgb, tint.a);

    float topGlow = pow(clamp(1.0 - vUv.y, 0.0, 1.0), 3.0) * 0.35;
    float edgeDist = min(min(vUv.x, 1.0 - vUv.x), min(vUv.y, 1.0 - vUv.y));
    float rim = smoothstep(0.06, 0.0, edgeDist) * 0.25;
    vec3 glass = tintedGlass + vec3(topGlow + rim);

    vec2 posPx = vUv * panelSizePx - panelSizePx * 0.5;
    float d = roundedRectSD(posPx, panelSizePx * 0.5, cornerRadiusPx);
    // A full device pixel of feathering on each edge. This was narrowed to
    // 0.35 for a while to fight a muddy-looking border, but that muddiness
    // was actually caused by borderWidthPx being only 1 device px (see
    // glass_hud.py's set_border call): the full-coverage plateau in the
    // band math below is (borderWidthPx - aa - aaInner) wide, which was
    // ~0 at 1px, so no pixel was *ever* fully opaque regardless of aa.
    // Narrowing aa didn't fix that -- it only shrank the transition zone to
    // under 1px, which made the crop boundary flip almost discontinuously
    // (0 -> 1 coverage) for any sub-device-pixel shift in the widget's own
    // on-screen position (confirmed live: two static frames, flyout
    // resting at two different sub-pixel offsets after being dragged,
    // showed a ~60/255 jump in the handful of pixels straddling that
    // boundary, while the border itself and the backdrop on either side
    // barely moved). Now that borderWidthPx is 2 and the plateau is
    // genuinely wide enough to be fully opaque, aa can go back to being
    // wide enough for position-stable antialiasing without the border
    // reading as muddy again.
    float halfBorder = borderWidthPx * 0.5;
    // No antialiasing at all: a hard step at d = halfBorder / d = -halfBorder
    // instead of smoothstep. Trades any softened edge (and the aliasing/
    // jaggies that come with removing it) for a fully deterministic
    // per-pixel classification -- every pixel is unambiguously border,
    // glass, or raw, with no partial-coverage blend zone to be sensitive to
    // sub-device-pixel shifts in the widget's own on-screen position (see
    // the smoothstep version's history above/in git blame: narrowing the
    // feather to fight muddiness made that blend zone under 1px wide and
    // it started visibly popping between two static, sub-pixel-different
    // resting positions of the same flyout). This still has a boundary
    // pixel that can flip which side it's on with a small position shift --
    // that's inherent to any single-sample-per-pixel rasterization -- but
    // the flip is now a clean 0-or-1 classification, not a mid-tone blend.
    float outsideMask = step(halfBorder, d);
    float innerMask = step(-halfBorder, d);
    float band = innerMask * (1.0 - outsideMask);

    if (debugViz > 0.5)
    {
        // red = outsideMask (fully-transparent crop), green = band (border
        // stroke coverage), blue = innerMask (fill->border transition).
        // A correct corner shows a clean, smoothly curved
        // black -> blue -> green -> red progression following the rounded
        // curve, with band's green ring a constant width all the way
        // around. Any speckling, a green ring that isn't constant width at
        // the corner vs. the flat edges, or red bleeding inside where
        // green/blue should be, marks exactly where in the mask math the
        // artifact comes from. Kept fully opaque here regardless of
        // outsideMask -- debugViz is about seeing the masks themselves, not
        // about testing the real alpha output.
        fragColor = vec4(outsideMask, band, innerMask, 1.0);
        return;
    }

    vec3 color = mix(glass, borderColor.rgb, band * borderColor.a);
    // Real transparency outside the rounded shape instead of an opaque
    // resample of the backdrop -- see this file's header comment. Qt
    // composites this widget normally against whatever's actually behind
    // it (canvas, another flyout, ...) using this alpha, the same as any
    // other translucent widget.
    float alpha = 1.0 - outsideMask;
    fragColor = vec4(color, alpha);
}
