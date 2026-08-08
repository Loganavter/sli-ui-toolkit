#version 440

// Fullscreen-triangle vertex shader for flyout_fill.frag. Three vertices
// covering the whole viewport (no vertex/index buffer needed) -- the
// standard "big triangle" trick, clipped to the viewport by the rasterizer.

layout(location = 0) out vec2 vUv;

void main()
{
    vec2 pos = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    vUv = pos;
    gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
}
