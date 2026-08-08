#version 440

// Shared fullscreen-triangle vertex shader for both liquid-glass passes
// (liquid_glass_blur.frag, liquid_glass_composite.frag). See flyout_fill.vert
// for the "big triangle" technique this copies -- kept as its own file
// since QShader is loaded per compiled .qsb, one per pipeline stage.

layout(location = 0) out vec2 vUv;

void main()
{
    vec2 pos = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    vUv = pos;
    gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
}
