#version 430 core

layout(location = 0) in vec2 vert;

layout(std430, binding = 0) buffer GaussianData {
    float gs_data[];
};
layout(std430, binding = 1) buffer GaussianOrder {
    uint gs_index[];
};
layout(std430, binding = 4) buffer PreviewOrder {
    uint preview_index[];
};

uniform mat4 view_matrix;
uniform mat4 projection_matrix;
uniform int data_sh_dim;
uniform int gs_num;
uniform int preview_mode;
uniform float sphere_sigma_multiplier;

out vec2 local_quad;
flat out vec3 sphere_center;
flat out float sphere_radius;
flat out vec3 gaussian_color;
flat out float gaussian_alpha;

const int OFFSET_DATA_POS = 0;
const int OFFSET_DATA_SCALE = 7;
const int OFFSET_DATA_ALPHA = 10;
const int OFFSET_DATA_SH = 11;
const float SH_C0_0 = 0.28209479177387814;

vec3 get_vec3(int offset)
{
    return vec3(gs_data[offset], gs_data[offset + 1], gs_data[offset + 2]);
}

void main()
{
    int instance_id = gl_InstanceID;
    int gs_id = preview_mode != 0 ? int(preview_index[instance_id]) : int(gs_index[instance_id]);
    int dim_gs = 3 + 4 + 3 + 1 + data_sh_dim;
    int base_gs = gs_id * dim_gs;
    vec3 world_center = get_vec3(base_gs + OFFSET_DATA_POS);
    vec3 scale = get_vec3(base_gs + OFFSET_DATA_SCALE);
    float radius = max(max(scale.x, scale.y), scale.z) * sphere_sigma_multiplier;
    vec4 view_position = view_matrix * vec4(world_center, 1.0);
    vec4 clip_position = projection_matrix * view_position;
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    if (gs_id < 0 || gs_id >= gs_num || view_position.z >= -0.0001 || clip_position.w <= 0.0)
        return;

    float camera_depth = max(-view_position.z, 0.0001);
    vec2 radius_ndc = abs(vec2(
        projection_matrix[0][0] * radius / camera_depth,
        projection_matrix[1][1] * radius / camera_depth
    ));
    vec2 center_ndc = clip_position.xy / clip_position.w;
    gl_Position = vec4(center_ndc + vert * radius_ndc, clip_position.z / clip_position.w, 1.0);
    local_quad = vert;
    sphere_center = view_position.xyz;
    sphere_radius = max(radius, 0.000001);
    gaussian_color = max(vec3(0.0), vec3(0.5) + SH_C0_0 * get_vec3(base_gs + OFFSET_DATA_SH));
    gaussian_alpha = clamp(gs_data[base_gs + OFFSET_DATA_ALPHA], 0.0, 1.0);
}
