#version 430 core

layout(location = 0) in vec3 position;
layout(location = 1) in vec4 vertex_color;

uniform mat4 view_matrix;
uniform mat4 projection_matrix;

out vec4 color;

void main()
{
    gl_Position = projection_matrix * view_matrix * vec4(position, 1.0);
    color = vertex_color;
}
