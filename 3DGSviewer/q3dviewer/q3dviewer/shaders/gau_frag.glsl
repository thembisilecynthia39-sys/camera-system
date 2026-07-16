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

out vec4 final_color;

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
    final_color = vec4(color * alpha_prime, alpha_prime);

    if (render_mod == 1)
    {
        float mask = alpha_prime > 0.3f ? 1.0f : 0.0f;
        if (mask == 0.0f)
            discard;
        final_color = vec4(color * g, mask);
    }
    else if (render_mod == 2)
    {
        float inverse_alpha = alpha_prime > 0.3f ? 1.0f - alpha_prime : 0.0f;
        if (inverse_alpha == 0.0f)
            discard;
        final_color = vec4(color * inverse_alpha, inverse_alpha);
    }
    

}
