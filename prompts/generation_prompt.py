"""Prompts for Task 5: LinkedIn Content Generator."""

GENERATION_SYSTEM_TEMPLATE = """You are a retail AI thought leader writing for LinkedIn.

Your audience: retail executives, digital strategy directors, e-commerce founders, and retail investors.
Your positioning: forward-thinking retail AI strategist who translates complex AI developments into
clear business implications for the retail sector.

## Style Model for This Post: {kol_name}
Write this post in the communication style of {kol_name}. Study and replicate their specific patterns:
{kol_profile}

## Broader Style Synthesis (additional context)
{kol_style_synthesis}

## Writing Rules
- Open with a pattern-interrupting hook in {kol_name}'s style — never start with "Excited to share..." or "I'm thrilled..."
- Connect the AI news to a SPECIFIC retail pain point or opportunity within the first 3 lines
- Offer a concrete, non-obvious insight or prediction that a retail executive would find actionable
- Use whitespace and short paragraphs for mobile readability (LinkedIn is 80%+ mobile)
- Occasional bullet points (3-4 max) are fine, but don't make the whole post a list
- End with a thought-provoking question that invites genuine engagement
- Length: 150-250 words (optimal for LinkedIn engagement)
- Tone: confident, specific, insight-driven — not generic AI hype
- Never use phrases like "game-changer", "revolutionary", "in today's fast-paced world", "leverage"
- Include 3-5 relevant hashtags as a separate list

Return ONLY a valid JSON object — no markdown, no extra text:
{{"post_text": "<the full LinkedIn post body, no hashtags>", "hashtags": ["#Tag1", "#Tag2", "#Tag3"]}}"""

GENERATION_USER_TEMPLATE = """Write a LinkedIn post based on this AI development:

Category: {category}
Article title: {title}
Source: {source}
Summary: {summary}

Target audience: Retail executives and digital strategy leaders.
Tone: Thought leadership — insight-sharing, not news reporting.

Make the retail angle specific and actionable.
Return JSON with keys: post_text and hashtags."""


# DALL-E image prompt per category
DALLE_PROMPTS = {
    "Customer Experience & Personalization": (
        "A warmly lit modern retail store where a diverse shopper interacts with a sleek AI-powered "
        "digital display showing personalized product recommendations. Photorealistic, professional "
        "editorial style, 16:9 format, no text overlays, no logos, no watermarks."
    ),
    "Supply Chain & Operations": (
        "An AI-powered distribution warehouse with autonomous robotic systems moving inventory, "
        "real-time data dashboards glowing on screens, clean industrial aesthetic, soft blue lighting. "
        "Photorealistic, professional editorial style, 16:9 format, no text overlays, no logos."
    ),
    "Pricing & Revenue Management": (
        "A dynamic retail pricing dashboard with flowing data visualizations and analytics graphs, "
        "abstract representation of revenue optimization, professional corporate aesthetic, "
        "deep teal and gold color palette. Digital art, 16:9, no text, no logos."
    ),
    "AI Infrastructure & Tools": (
        "Abstract visualization of interconnected AI neural networks overlaid on a glowing retail "
        "cityscape at night, deep blues and purples, futuristic but professional. "
        "Digital art, 16:9 format, no text overlays, no logos, no watermarks."
    ),
    "Governance, Ethics & Regulation": (
        "A professional corporate boardroom with diverse executives reviewing AI compliance documents, "
        "digital data displays on walls, balanced scales as a subtle visual motif, "
        "authoritative and serious tone. Photorealistic, 16:9, no text overlays, no logos."
    ),
}

DEFAULT_DALLE_PROMPT = (
    "Professional business visualization of artificial intelligence transforming the retail industry, "
    "modern aesthetic, photorealistic, 16:9 format, no text overlays, no logos."
)

DEFAULT_HASHTAGS = ["#RetailAI", "#AIinRetail", "#DigitalRetail", "#RetailTech"]


def get_dalle_prompt(category: str, article_title: str) -> str:
    base = DALLE_PROMPTS.get(category, DEFAULT_DALLE_PROMPT)
    context = f"Visual context: {article_title[:80]}."
    return f"{base} {context}"
