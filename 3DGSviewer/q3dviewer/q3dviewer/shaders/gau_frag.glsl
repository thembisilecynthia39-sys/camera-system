#version 430 core
/*
this file is modified from GaussianSplattingViewer licensed under the MIT License.
see https://github.com/limacv/GaussianSplattingViewer/blob/main/shaders/gau_frag.glsl
*/


in vec3 color;
in float alpha;
in vec3 cinv2d;
in vec2 d_pix;  // u - pix

uniform int  render_mod = 1;
uniform vec2 win_size;
uniform float appearance_exposure = 0.0;
uniform int appearance_tone_mapping = 2;
uniform float appearance_contrast = 1.0;
uniform float appearance_saturation = 1.0;
uniform float appearance_vignette = 0.0;

out vec4 final_color;

vec3 apply_appearance(vec3 value)
{
    value *= exp2(clamp(appearance_exposure, -20.0, 20.0));
    if (appearance_tone_mapping == 2)
    {
        value = (value * (2.51 * value + 0.03)) /
                (value * (2.43 * value + 0.59) + 0.14);
    }
    else if (appearance_tone_mapping == 1)
    {
        value = value / (1.0 + value);
    }
    value = (value - 0.5) * appearance_contrast + 0.5;
    float luminance = dot(value, vec3(0.2126, 0.7152, 0.0722));
    value = mix(vec3(luminance), value, appearance_saturation);
    vec2 uv = gl_FragCoord.xy / win_size;
    float radius = distance(uv, vec2(0.5)) * 1.41421356;
    value *= 1.0 - appearance_vignette * clamp(radius * radius, 0.0, 1.0);
    return clamp(value, 0.0, 1.0);
}

void main()
{
    if (alpha < 0.001)
        discard;
    float maha_dist = cinv2d.x * d_pix.x * d_pix.x + cinv2d.z * d_pix.y * d_pix.y + 2 * cinv2d.y * d_pix.x * d_pix.y;
    const float cutoff_dist = 9.0f;
    if (maha_dist < 0.f || maha_dist >= cutoff_dist)
        discard;

    const float cutoff_weight = exp(-0.5f * cutoff_dist);
    float g = (exp(-0.5f * maha_dist) - cutoff_weight) /
              (1.0f - cutoff_weight);
    float alpha_prime = min(0.99f, alpha * g);
    if (alpha_prime < 1.f / 255.f)
        discard;
    vec3 shaded_color = apply_appearance(color);
    final_color = vec4(shaded_color * alpha_prime, alpha_prime);

    if (render_mod == 1)
    {
        float mask = alpha_prime > 0.3f ? 1.0f : 0.0f;
        if (mask == 0.0f)
            discard;
        final_color = vec4(shaded_color * g, mask);
    }
    else if (render_mod == 2)
    {
        float inverse_alpha = alpha_prime > 0.3f ? 1.0f - alpha_prime : 0.0f;
        if (inverse_alpha == 0.0f)
            discard;
        final_color = vec4(shaded_color * inverse_alpha, inverse_alpha);
    }
    

}
