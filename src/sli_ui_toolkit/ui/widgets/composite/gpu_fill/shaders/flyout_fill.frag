#version 440

// Flat-color fill for BaseFlyout's GPU rendering path (see gpu_fill/widget.py).
// Straight (non-premultiplied) alpha out -- matches the pipeline's
// SrcAlpha/OneMinusSrcAlpha blend factors.

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
