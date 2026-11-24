#version 440

// Flat-color fill for BaseFlyout's GPU rendering path (see gpu_fill/widget.py).
// The pass is opaque: the pipeline requests no blend state and the widget
// overwrites the raster siblings under it, so alpha here would only reach the
// blit, not blend against anything.

layout(std140, binding = 0) uniform UBuf
{
    vec4 fillColor;
};

layout(location = 0) in vec2 vUv;
layout(location = 0) out vec4 fragColor;

void main()
{
    fragColor = fillColor;
}
