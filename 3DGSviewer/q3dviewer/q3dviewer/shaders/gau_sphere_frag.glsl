#version 430 core

in vec2 local_quad;
flat in vec3 sphere_center;
flat in float sphere_radius;
flat in vec3 gaussian_color;
flat in float gaussian_alpha;

uniform mat4 inverse_projection_matrix;
uniform mat4 projection_matrix;
uniform vec2 win_size;
uniform float sphere_opacity;
uniform float line_width;
uniform int render_style;
uniform int color_mode;
uniform vec3 uniform_color;

out vec4 final_color;

void main()
{
    vec2 ndc = gl_FragCoord.xy / win_size * 2.0 - 1.0;
    vec4 ray_point = inverse_projection_matrix * vec4(ndc, -1.0, 1.0);
    vec3 ray = normalize(ray_point.xyz / ray_point.w);
    vec3 sphere_to_camera = -sphere_center;
    float ray_projection = dot(ray, sphere_to_camera);
    float ray_distance_sq = dot(sphere_to_camera, sphere_to_camera) - sphere_radius * sphere_radius;
    float discriminant = ray_projection * ray_projection - ray_distance_sq;
    if (discriminant < 0.0)
        discard;

    float root = sqrt(discriminant);
    float hit_distance = -ray_projection - root;
    if (hit_distance <= 0.0)
        hit_distance = -ray_projection + root;
    if (hit_distance <= 0.0)
        discard;
    vec3 hit = ray * hit_distance;
    vec3 normal = normalize(hit - sphere_center);
    vec4 projected_hit = projection_matrix * vec4(hit, 1.0);
    gl_FragDepth = projected_hit.z / projected_hit.w * 0.5 + 0.5;

    vec3 color = color_mode == 0 ? gaussian_color : uniform_color;
    float alpha = max(gaussian_alpha, 0.15) * sphere_opacity;
    if (render_style != 1)
    {
        float latitude = abs(sin(asin(clamp(normal.z, -1.0, 1.0)) * 8.0));
        float longitude = abs(sin(atan(normal.y, normal.x) * 8.0));
        float band = max(fwidth(latitude), fwidth(longitude)) * max(line_width, 1.0);
        float wire = max(1.0 - smoothstep(0.0, band + 0.02, latitude),
                         1.0 - smoothstep(0.0, band + 0.02, longitude));
        float silhouette = 1.0 - smoothstep(0.0, fwidth(local_quad.x) * max(line_width, 1.0) + 0.02,
                                             abs(1.0 - dot(local_quad, local_quad)));
        wire = max(wire, silhouette);
        if (wire < 0.05)
            discard;
        alpha *= wire;
    }
    final_color = vec4(color * alpha, alpha);
}
