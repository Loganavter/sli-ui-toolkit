#version 440

// Pass 1 of LiquidGlassFillWidget's 2-pass separable blur (horizontal;
// liquid_glass_composite.frag does the vertical half + tint + rim). A real
// discrete Gaussian -- one independent `texture()` fetch per tap at exact
// texel-center offsets, weighted by the actual Gaussian bell curve for the
// requested radius -- not the "efficient" 5-tap linear-sampled
// approximation this used to be (that trick leans on the sampler's own
// bilinear blend between texel pairs to halve the fetch count, which reads
// as a flat/"linear" look rather than a proper soft falloff once the
// radius is small relative to a texel). More fetches (17 here), but this
// runs over a small HUD-panel-sized scratch target, not a full screen.
//
// srcTex is the *live* source widget's own colorTexture() (e.g. the main
// canvas QRhiWidget) sampled directly GPU-side -- no CPU readback. Since
// this pass draws into a small scratch target sized to just this HUD
// panel, not the whole source texture, uvOffset/uvScale map this pass's
// own [0,1] output UV into the small sub-rect of the (much larger) source
// texture that sits behind the panel on screen.

layout(std140, binding = 0) uniform UBuf
{
    vec2 direction;
    float radiusPx;
    float _pad0;
    vec2 uvOffset;
    vec2 uvScale;
};

layout(binding = 1) uniform sampler2D srcTex;

layout(location = 0) in vec2 vUv;
layout(location = 0) out vec4 fragColor;

const int TAPS = 8; // -8..8 inclusive => 17 samples

void main()
{
    // srcTex is a *foreign* widget's own colorTexture() (the canvas), read
    // directly off the GPU -- not something Qt has composited to screen for
    // us. A shown QRhiWidget's backend Y-convention mismatch (if any) is
    // normally absorbed for free by its own backing-store blit to the
    // actual screen surface (see docs/dev/rendering/coordinate-systems.md
    // "Offscreen scissor Y-flip" / qrhi-gotchas.md's mip-cascade writeup for
    // the same class of bug); bypassing that blit to sample the texture's
    // raw content ourselves means we get its *un*-corrected, backend-native
    // row order instead. Unconditional flip, not a rhi.isYUpInFramebuffer()
    // check -- this project's own mip-cascade fix for the identical
    // situation found isYUpInFramebuffer()/clipSpaceCorrMatrix() to be a
    // no-op (identity) for this project's OpenGL backend/widget context, so
    // conditioning on it would just silently skip the correction.
    // Flip the *fully resolved* Y position (after adding uvOffset), not
    // vUv.y before scaling -- the latter only mirrors within this pass's
    // own small sub-rect and leaves uvOffset.y's contribution unflipped,
    // landing on a v-coordinate with no relation to the correct mirrored
    // row once uvOffset.y != 0 (always true; this HUD panel is never at
    // the source texture's very top row).
    vec2 srcUv = uvOffset + vUv * uvScale;
    srcUv.y = 1.0 - srcUv.y;
    // Texel step in the *source* texture's own resolution -- radiusPx is
    // therefore a real device-pixel blur spread on screen, independent of
    // how small a fraction of the source uvScale covers.
    vec2 texel = direction / vec2(textureSize(srcTex, 0));
    float sigma = max(radiusPx / 3.0, 0.6);

    vec4 sum = vec4(0.0);
    float weightSum = 0.0;
    for (int i = -TAPS; i <= TAPS; i++)
    {
        float fi = float(i);
        float w = exp(-(fi * fi) / (2.0 * sigma * sigma));
        sum += texture(srcTex, srcUv + texel * fi) * w;
        weightSum += w;
    }

    fragColor = sum / max(weightSum, 1e-5);
}
