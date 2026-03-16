# PROMPT 53C: Landing Page Polish + Pricing Fix + Loading Humor

*Read CLAUDE.md first. HTML + CSS + one small JS addition. No backend model changes.*

---

## Problem Statement

Three issues:
1. Landing page looks like a template — needs visual punch, copy cleanup, and the 4-card grid wraps to 3+1 (asymmetric)
2. Pricing tiers are wrong — Starter is too generous, user counts invite abuse
3. The quote generation takes several minutes but there's no entertaining feedback — users think it's broken

---

## Changes Required

### 1. Feature Grid: 2x2 Grid (Symmetry Fix)
Keep all 4 feature cards but force a **2x2 grid** — two rows, two columns. No orphan card.

**Force 2x2 layout on desktop:** `grid-template-columns: repeat(2, 1fr)` — no auto-fit wrapping. Stacks to 1 column on mobile.

Keep the 4 cards but clean up the copy (remove "AI" from descriptions):

**Card 1: "Describe It. We'll Quote It."**
- Icon: 🔥
- "Type a plain-English description or upload photos. Gates, railings, stairs, bumpers, LED signs, trailers — 25+ job types understood instantly."

**Card 2: "Accurate Down to the Stick"**
- Icon: ⚙️
- "Real cut lists with material profiles, stock lengths, and waste factors. Labor hours broken down by process — fit & tack, welding, grinding, finishing. Not generic estimates."

**Card 3: "Three Downloads. One Quote."**
- Icon: 📄
- "Get a clean customer quote to send your client, detailed shop build instructions for your crew, and an organized material list ready to email your steel distributor. All branded with your shop name and logo."

**Card 4: "Built for the Shop Floor"**
- Icon: 🔧
- "Weld process detection, TIG vs MIG routing, finish types, stock length optimization. This tool knows how fab shops actually work — because fabricators built it."

### 2. Hero Section Visual Upgrade
- Add a **subtle radial gradient** to the hero background — dark center fading to slightly lighter edges. Not flat black.
- Add a **subtle grid/mesh pattern overlay** using CSS (repeating-linear-gradient) — industrial/technical feel without loading an image.
- Make the "AI-Powered" part of the h1 slightly smaller/lighter weight than "Metal Fabrication Quoting" — the product is the star, AI is the method.

CSS for the hero background:
```css
.hero {
    background: 
        linear-gradient(rgba(15,23,42,0.95), rgba(15,23,42,0.98)),
        repeating-linear-gradient(
            0deg, transparent, transparent 50px,
            rgba(59,130,246,0.03) 50px, rgba(59,130,246,0.03) 51px
        ),
        repeating-linear-gradient(
            90deg, transparent, transparent 50px,
            rgba(59,130,246,0.03) 50px, rgba(59,130,246,0.03) 51px
        );
    background-color: #0f172a;
}
```

### 3. Copy: Remove "AI" Everywhere Except Hero
- Hero headline: "AI-Powered Metal Fabrication Quoting" — **KEEP this, it's the one AI mention**
- Feature cards: NO "AI" — describe the result, not the method
- How It Works: Replace "The AI extracts dimensions..." → "Dimensions, materials, and finish requirements are extracted automatically."
- Section title: "Everything You Need to Quote Faster" → **"Stop Guessing. Start Quoting."**
- Footer: "AI-powered quoting for metal fabrication" → "Professional quoting software for metal fabrication shops."

### 4. Feature Cards Visual Upgrade
- Add **colored top border** to each card (3px, accent blue)
- Slightly larger icons
- Subtle hover lift: `transform: translateY(-2px)` on hover

### 5. How It Works: Add Connecting Lines
Between the 3 step circles, add a subtle dashed line connecting them horizontally (CSS pseudo-elements).

### 6. CTA Button Polish
- "Get Started" → **"Start Quoting Free"**
- "See How It Works" → **"See How It Works ↓"**
- Make the primary CTA bigger and bolder

### 7. Pricing Overhaul — New Tiers
Replace the entire pricing section with these tiers. **NO mention of users anywhere.** One account = one shop = one login.

**Starter — $49/mo**
- 3 quotes per month
- PDF downloads
- Email support

**Professional — $149/mo** (Most Popular)
- 25 quotes per month
- Shop branding on PDFs
- Bid document parser
- Priority support

**Shop — $349/mo**
- Unlimited quotes
- API access
- Custom integrations
- Dedicated support

Update the HTML in the pricing section. Remove ALL references to "users" or "seats" from the pricing cards.

### 8. Quote Loading Screen — Rotating Funny Messages + "Stay on this page"

This is the fun one. In `frontend/js/quote-flow.js`, find the processing/loading state that shows while the quote is generating. Add a **rotating message system** that cycles through funny fabrication-themed messages every 8-10 seconds, plus a persistent reminder to stay on the page.

**Add this array of messages** (the JS should pick randomly, never repeat the same one back-to-back):

```javascript
const LOADING_MESSAGES = [
    // Famous sayings, metal fabricated
    "Rome wasn't metal fabricated in a day... 🏛️",
    "That's one small weld for man, one giant quote for fabrication... 🚀",
    "To grind, or not to grind — that is the question... 🎭",
    "Ask not what your shop can quote for you, ask what you can fabricate for your shop... 🇺🇸",
    "I came, I saw, I fabricated... ⚔️",
    "Houston, we have a cut list... 🌙",
    "A journey of a thousand welds begins with a single tack... 🔥",
    "Float like a butterfly, weld like a bee... 🥊",
    "In the beginning, there was mild steel. And it was good... 📖",
    "May the flux be with you... ⚡",
    "You miss 100% of the quotes you don't generate... 🏒",
    "It's not about how hard you grind, it's about how hard you can get ground and keep fabricating... 🥊",
    "One does not simply walk into a fab shop without a quote... 🧙",
    "With great welding comes great responsibility... 🕷️",
    "Life is like a box of steel — you never know what gauge you're gonna get... 🍫",
    "I'll be back... with your quote... 🤖",
    "Here's looking at you, fabricator... 🎬",
    "To infinity and beyond — but first, let me finish this cut list... 🚀",
    "The first rule of Fab Club: always get a quote first... 🥊",
    "Keep your friends close and your tape measure closer... 📏",
    "Winter is coming — better quote that gate before frost line season... 🥶",
    "I'm gonna make you a quote you can't refuse... 🎩",
    "That which does not kill your budget makes your shop stronger... 💪",
    "Elementary, my dear fabricator — the numbers don't lie... 🔍",
    "It was the best of welds, it was the worst of welds... 📚",
    "Not all who wander are lost — some are just looking for the right profile key... 🗺️",
    "A fabricator's work is never done, but your quote almost is... ⏳",
    "Why so serious? Your quote will be ready soon... 🃏",
    "Frankly my dear, I don't give a slag... 🎬",
    "I see dead drops... and I'm optimizing them out of your cut list... 👻",
];
```

**Display format:**
- Show the spinner (keep existing)
- Below the spinner, show the rotating message in a slightly larger, friendly font
- Below THAT, show a persistent subtle line: **"Hold tight — don't leave this page while your quote generates."**
- Message rotates every 8 seconds with a smooth fade transition

**CSS for the loading messages:**
```css
.loading-message {
    font-size: 1.1rem;
    color: var(--text-secondary);
    margin-top: 20px;
    min-height: 2em;
    transition: opacity 0.5s ease;
}
.loading-stay {
    font-size: 0.85rem;
    color: var(--text-light);
    margin-top: 12px;
    font-style: italic;
}
```

---

## Constraint Architecture

### Files to MODIFY
- `frontend/index.html` — copy changes, 3 feature cards, new pricing tiers
- `frontend/css/landing.css` — hero gradient, card borders, hover effects, grid fix
- `frontend/js/quote-flow.js` — add loading message rotation system
- `frontend/css/style.css` — add loading message styles

### DO NOT TOUCH
- `frontend/app.html`, `frontend/js/auth.js`, `frontend/js/api.js`
- Any backend files — no model changes, no route changes
- Existing test files

---

## Session Discipline
- **Chunk 1:** Landing page HTML + CSS changes (features, pricing, hero, copy) → COMMIT
- **Chunk 2:** Loading message rotation in quote-flow.js + CSS → COMMIT
- Run `pytest tests/ -v | tail -5` after each chunk
- Push when both are done

---

## Evaluation
1. Landing page: hero has subtle grid pattern, not flat black
2. Feature section: 2x2 grid on desktop (two rows, two columns)
3. "AI" appears only once (hero headline) on the landing page
4. Pricing: 3 tiers with correct quote limits, NO mention of users/seats
5. Cards have colored top border + hover lift
6. Start a quote → processing screen shows rotating funny messages
7. Messages change every ~8 seconds with fade
8. "Don't leave this page" reminder is always visible during generation
9. Mobile: still responsive, cards stack to 1 column
