# Templates for kitcut.ai: which niches, industries and use cases

Researched 2026-10-02. Sources:
- Google Keyword Planner, through our own Ads account: 1,401 keywords, then about 2,070 with the
  "ai" and "template" versions.
- HeyGen's live site, sitemap, pricing and customer stories.
- The template catalogues of 13 animated and template video tools.
- Freelance marketplaces and agency price lists.
- Industry surveys.

Every number carries its source. A vendor's claim about itself is marked **[own claim]**.

This doc is the basis for growing the template library from the 5 event templates (speaker
promo, in numbers, agenda, call for speakers, ride replay) to 150+. A template is a finished example
film that a person remakes with a free prompt ([[kitcut-templates]] in the memory; `config/templates/`).

## The findings in one page

1. **Searches and money are in different places.**
   - Search volume sits in three groups:
     - tool searches: "ai video generator" 1.5M/mo, "animated video maker" 27k;
     - personal occasions: "wedding invitation video" 27k, "birthday video maker" 12k;
     - kids' and channel content.
   - Money sits in business niches: training, HR, SaaS, legal and nonprofits, where advertisers
     bid **$15–72 a click**.
   - Almost nobody searches the industry phrase itself. "Insurance explainer video", "release notes
     video" and "real estate market update video" each get **under 10 searches a month**.
   - Businesses search for a supplier ("explainer video production", bids up to $42.57; "law firm
     marketing video", $48.58), not for a template.
   - **So industry templates will not bring search traffic.** They are sales material for ads,
     outreach and agencies. The search traffic comes from consumer, kids', creator and "maker"
     pages.
2. **HeyGen's paying base is small business, plus enterprise training.**
   - $200M a year in revenue (June 2026; Upstarts from company figures) and 30M users **[own claim]**.
   - Its payers are "small business owners, real estate agents, personal trainers, online course
     instructors" (Upstarts, CEO interview); mid-market is 44% of its customers (Ramp).
   - It also sells enterprise training and localization (Workday, Coursera, Komatsu, Würth).
   - Its biggest objection among people who don't use it is *"worried about looking fake"*,
     at 50.7% (HeyGen's own survey of 1,000+ SMB owners, 2026-09).
3. **We overlap with HeyGen wherever a presenter is not the point**: training scenes, product and
   process explainers, patient education, history/news/faith storytelling, kids, faceless channels,
   event promos, memorials. We should not chase UGC-style ads, personalised sales videos, live
   avatars, or dubbing of real footage. That is HeyGen's home ground.
4. **HeyGen is building our product.**
   - HyperFrames (open source, 2026-04-17) is the same architecture as ours: an agent writes
     HTML/CSS and headless Chrome renders it to MP4.
   - It has been inside HeyGen's Video Agent since 2026-07, together with website-to-video.
   - HeyGen also retired its public template gallery: heygen.com/templates now redirects to
     /agent, and its sitemap of templates returns 410. It wins search through ~130
     "/tool/<x>-video-maker" pages instead.
   - **Our moat therefore cannot be "prompt to explainer".** It has to be:
     - the look (drawn, collage, painted);
     - real people drawn from their photos;
     - maps, routes and data;
     - depth in each niche.
5. **The gaps in 13 competitors' catalogues** (Vyond, Powtoon, VideoScribe, Doodly, Animaker,
   Renderforest, Biteable, Moovly, Steve.ai, Canva, InVideo, Pictory, Lumen5):
   - **Events beyond the invitation.** None names speaker line-ups, agendas or a call for
     speakers, yet Renderforest's "Event Promo Story" has 349K+ exports.
   - **"In numbers" / year in review.** Named by only 4 tools; Renderforest's "Company Year-In-Review"
     has 294K+ exports.
   - **Maps and routes.** One tool; Renderforest's "World Map Video Toolkit" has 40K+ exports.
   - **Kids' series.** Three tools.
   - **Developer content.** None.
   - **Real people drawn from photos.** None.

   We already sit in events and maps.
6. **Organise templates as three portfolios, and score each on its own number:**
   - **Habit:** formats people need every week. This fixes our biggest gap: 0 people had come
     back on another day by day 5 ([[kitcut-traction-baseline]]).
   - **Revenue:** niches that already pay a subscription for ready-made video.
   - **Reach:** personal occasions. Every guest who opens an invitation sees the film.
7. **"ai" and "template" versions** (section 1a):
   - People search for the job ("wedding invitation video" 27,100), not the technology ("ai …"
     1,600) or the template ("… templates" 5,400).
   - The exceptions are creators, where the "ai" phrase is the search: "ai video generator for
     youtube" 4,400, up 4×; "ai story video generator" 2,900.
   - The fastest risers are "ai birthday invitation" (3.3×) and "ai real estate video" (1.9×).
   - "Video templates" (40,500) and "AI video templates" (880) both grow, and name what our
     gallery is.
8. **The calendar matters now.** On 2026-10-02 the next peaks are:
   - US benefits open enrollment (October–November);
   - Halloween;
   - Black Friday;
   - holiday cards and year-in-review films (December).

## 1. Search demand, measured (Google Keyword Planner)

**How it was measured:**
- Average monthly searches over the last 12 months, plus Google's top-of-page bid range: what
  advertisers pay for the top slot, our best stand-in for what a click is worth to a business.
- The tool cannot choose a country, so these are the planner's defaults. "heygen" at 1.5M a month
  suggests the figures are worldwide.
- "<10" means the planner returned nothing for the phrase.
- Raw dumps were in the session's tool-results; the parser was `temp/kw-parse.mjs`, gitignored.

**Brands and tool searches** (the head of the market):

| Search | / month | Top bid |
|---|---:|---:|
| ai video generator | 1,500,000 | $1.48 |
| heygen | 1,500,000 | $2.45 |
| synthesia | 368,000 | $3.14 |
| powtoon | 165,000 | $1.31 |
| ai video maker | 165,000 | $2.30 |
| vyond | 135,000 | $3.68 |
| text to video ai | 135,000 | $0.49 |
| animate photo | 60,500 | $2.60 |
| videoscribe | 40,500 | $1.59 |
| animated video maker / cartoon video maker | 27,100 each | $0.67 |
| how to make animated videos | 14,800 | $1.74 |
| ai cartoon video generator | 9,900 | $0.44 |
| explainer video | 6,600 | $13.06 |
| whiteboard animation | 6,600 | $4.71 |
| turn photo into cartoon | 5,400 | $3.84 |
| talking photo / talking avatar | 4,400 each | $0.88 / $1.37 |
| explainer video maker | 1,300 | $10.58 |
| explainer video production | 880 | $42.57 |
| animated explainer video company | 880 | $47.75 |

**By niche.** These are the head phrases each niche query returned.

| Niche | Head searches (/ month, top bid) | Phrases under 10 a month |
|---|---|---|
| Personal occasions | wedding invitation video 27,100 ($0.36); birthday video maker 12,100 ($0.30); invitation video maker 6,600 ($0.52); thank you video 3,600 ($1.76); save the date video 2,900 ($2.25); funeral slideshow 1,900 ($4.13); engagement video 1,900; birthday invitation video 1,900; gender reveal video 1,600; memorial video 880; graduation video 880; retirement video 590; memorial slideshow maker 210 ($6.27) | baby shower invitation video |
| Kids (watching) | nursery rhymes 301,000; bedtime stories 246,000; bedtime stories for kids 110,000; potty training video 3,600 ($3.32); nursery rhymes video 2,900 ($3.43); bedtime story video 390; animated story maker 390 | children's story video |
| Faceless channels | youtube automation 27,100 ($1.85); faceless youtube channel 6,600; history video 6,600 ($2.98); youtube shorts maker 5,400; fun facts video 2,900; animated documentary 720; book summary video 40 | news explainer video, reddit story video |
| Education | lesson video 1,900 ($3.97); online course video 1,300 ($5.56); classroom video 1,000; animated lesson 210 ($8.23); educational video maker 170 ($7.55) | math explainer video |
| Workplace training | training video 49,500 ($21.61); harassment video 1,600; forklift training video 880; training videos for employees 590 ($37.91); safety training video 480 ($18.00); ai training video generator 390 ($35.49); cyber security training videos 170 ($22.79); harassment training videos for employees 40 ($65.90); compliance training video 40 ($34.53) | — |
| HR and internal comms | recruitment video 1,000 ($14.43); onboarding video 590 ($19.49); company culture video 140 ($26.83); internal communications video 110 ($37.26); employee onboarding video 50 ($30.14) | — |
| SaaS and tech | demo video 4,400 ($8.72); saas explainer video 880 ($9.50); product launch video 720 ($11.13); product demo video 590 ($9.99); software explainer video 210; tech explainer video 140 ($11.89); tutorial video maker 110 ($14.16); b2b explainer video 70 ($55.02); startup pitch video 50 ($18.75) | release notes video, feature announcement video, product update video, investor pitch video |
| Events | speaker announcement 3,600 ($0.55); call for speakers 2,400 ($6.94); event promo video 210 ($5.42); event recap video 170; event highlight video 140 ($5.95); event teaser video 70 ($6.68); conference promo video 50 ($8.73) | — |
| Me, drawn | animate photo 60,500 ($2.60); cartoon me 18,100; turn photo into cartoon 5,400 ($3.84); talking photo 4,400; talking avatar 4,400; talking head video 2,900 ($4.50); cartoon yourself 1,900; make photo talk 1,900 | photo to cartoon video (10) |
| Small business | bakery video 2,400; menu video 320; grand opening video 210; video production for small businesses 210 ($12.70); small business video 140 ($12.29); promotional videos for small business 90 ($14.35) | salon/store promo video |
| Real estate | real estate video 4,400 ($6.18); open house video 2,900; real estate video editing 1,000 ($8.41); home tour video 720; video marketing for real estate 390 ($12.13); real estate agent video 320; real estate listing video 70 ($10.87) | real estate market update video |
| Finance and insurance | stock market video 1,300; financial literacy video 210 ($5.33); personal finance video 110 | insurance explainer video, crypto explainer video, investing/tax/mortgage explainer video |
| Healthcare | medical animation 1,300 ($11.92); dental video 880 ($8.26); nutrition video 590 ($7.17); dental patient education materials 480 ($9.15); veterinary video 320 ($10.03); patient education video 210 ($9.86); medical explainer video 50 ($11.71) | mental health video |
| Legal | law firm marketing video 170 ($48.58); video marketing for lawyers 170 ($55.21); law firm video 110 ($19.93) | legal explainer video |
| Nonprofit and public sector | public service announcement video 1,900; charity video 320 ($7.79); nonprofit video 210 ($17.71); fundraising video 170 ($17.28); donor thank you video 20 ($71.59) | impact report video, election explainer video |
| Faith | sermons on YouTube 2,400 ($20.00); church video 1,900 ($3.30); sermon video 390; church announcement video 170 ($4.41); church countdown video 170 | — |
| Media and podcasts | podcast video 12,100 ($8.36); podcast clips 1,300; magazine video 880; news video maker 390; book trailer maker 260 ($7.78); newsletter video 110 ($13.37) | — |
| Travel, maps and sport | animated travel map 3,600 ($0.72); cycling video 2,900 ($8.35); tour video 880; travel video maker 390; route animation 320; map animation video 260 | travel itinerary video |
| Reports and data | infographic video 1,900 ($4.56); statistics video 320; year in review video 170; data visualization video 70 | animated chart video |
| E-commerce and ads | ugc video 18,100 ($6.02); unboxing video 8,100; ugc ads 6,600 ($10.24); ecommerce video 720; product video maker 590; shopify product video 50 ($31.40) | — |

**What to take from it:**
- **Consumer phrases have volume but cheap clicks.** Business phrases have tiny volume but
  expensive clicks.
- **Kids' and channel phrases measure audience, not makers.** "Bedtime stories" at 246k is people
  looking for something to watch; that is the market a kids' channel sells into.
- **Search demand is not the reason to build an industry template.** The reason is the buyer's
  budget and how often they need a film.

## 1a. The same niches with "ai" and with "template" (measured 2026-10-02)

**How it was measured:** 17 more planner queries, about 2,070 keywords in all. Each row compares
the plain phrase, the "ai …" version and the "… template(s)" version. Each cell is monthly
searches and the top bid. "—" means the planner returned nothing, i.e. under 10 a month.

**Trend** is the last three months (Jun–Aug 2026) against the first three (Sep–Nov 2025). For
seasonal phrases (weddings, Christmas, training), trend mostly measures the season.

| Niche | Plain | With "ai" | With "template(s)" |
|---|---|---|---|
| Video in general | — | ai video generator **1,500,000** ($1.48, trend 1.5×) | video templates **40,500** ($1.54, 1.8×); capcut template 9,140,000 (2.9×) |
| The product category itself | — | **ai video templates 880** ($2.20, 1.2×) | — |
| Animated / cartoon | animated video maker 27,100 ($0.67) | ai animated video generator 9,900 ($2.30); ai cartoon video generator 9,900 | animated video templates 390 ($4.43) |
| Explainer | explainer video 6,600 ($13.06) | ai explainer video 1,000 ($7.35) | explainer video templates 210 ($4.56) |
| Whiteboard | whiteboard animation 6,600 ($4.71) | ai whiteboard animation 210 | whiteboard animation templates 20 |
| Wedding invitation | 27,100 ($0.36) | 1,600 ($0.30) | **5,400** (+9,900 "…free download") |
| Birthday | birthday video maker 12,100 ($0.30) | ai birthday video maker 1,900; ai birthday video 390 (1.6×) | birthday video templates **2,900** (1.3×) |
| Birthday invitation | 1,900 ($0.95) | **ai birthday invitation 590, trend 3.3×** (320 → 1,300 a month) | 210 |
| Save the date | 2,900 ($2.25) | 10 | 720 |
| Anniversary | 1,900 | 10 | 590 |
| Graduation | 880 | 10 | 170 (1.8×) |
| Retirement | 590 ($5.06) | — | 140 |
| Memorial | memorial video 880; funeral slideshow 1,900 ($4.13) | 20 ($7.00) | memorial 70; funeral tribute 110 |
| Christmas | christmas video card 480 | 140 (1,300 in December) | 170 (seasonal) |
| Thank-you | 3,600 ($1.76) | — | — |
| Kids' stories | bedtime story video 390 | **ai story video generator 2,900** ($0.65) | story video template 30 |
| History / documentary | history video 6,600; animated documentary 720 | ai documentary maker 170 | documentary template 210 |
| YouTube Shorts / channels | youtube shorts maker 5,400 (3.0×); faceless youtube channel 6,600 | **ai video generator for youtube 4,400 (4.0×)**; ai youtube shorts generator 1,900 (1.7×); ai faceless video 210 | youtube video templates 2,400; youtube shorts templates 1,600 |
| Education | lesson video 1,900; educational video maker 170 | ai educational video generator 210 ($5.52); ai teacher video 90 | educational video templates 50 |
| Workplace training | training video 49,500 ($21.61) | ai training videos 590 ($22.66); ai training video generator 390 (**$35.49**, 0.5×) | training video templates 170 ($7.67, **5.8×**) |
| Safety / onboarding / recruitment | 480 ($18) / 590 ($19.49) / 1,000 ($14.43) | — / — / — | — / 20 ($11.04) / 10 ($13.84) |
| Testimonial | 4,400 ($21.37) | — | 260 ($12.78) |
| Product | product launch video 720 ($11.13); product video maker 590 | ai product video 880 ($8.11) | product video templates 140; launch 50 |
| Ads | ad video maker 2,900 ($7.67) | ai ad generator 6,600 ($13.16); ai ad maker 3,600 ($15.59); ai ad creator 1,300 ($21.66) | video ad templates 390 ($5.86) |
| Real estate | real estate video 4,400 ($6.18) | **ai real estate video 320** ($10.17, 1.9×); ai listing video 20 ($16.18, new since March 2026) | real estate video templates 260 ($4.55) |
| Church | church video 1,900; sermon video 390 | 10 | church announcement template 390 ($4.93) |
| Podcast | podcast video 12,100 ($8.36) | 110 ($7.47) | 170 |
| Events | speaker announcement 3,600; call for speakers 2,400 ($6.94); event promo video 210 | ai invitation video maker 390; ai event / conference video — | countdown video template 260; event recap 70; event promo 50; speaker announcement 30; call for speakers 10 |
| Maps and travel | animated travel map 3,600; map animation video 260 | ai map animation 320 | travel video template 320; map animation template 70 |
| Infographic / year in review | infographic video 1,900; year in review video 170 | 20 / — | 110; year recap video template 140 |
| Photo → character | turn photo into cartoon 5,400; talking photo 4,400; cartoon yourself 1,900 | ai caricature 5,400 (1.4×); ai talking photo 3,600 (**0.4×**); ai photo to cartoon 590 (0.4×) | — |
| Medical, legal, nonprofit, insurance, restaurant, small business | 50–1,300 (bids $9–20) | ≤10 each | ≤40 each |

**What it means:**

1. **People search for the job, not the technology.**
   - In most niches the "ai" version is 5–30% of the plain phrase:
     - wedding invitation video: 27,100 plain, 1,600 with "ai";
     - explainer video: 6,600 against 1,000;
     - training video: 49,500 against 390–590.
   - Lead every page title with the job; "AI" goes second.
2. **Three exceptions, where the "ai" phrase is the search:**
   - **stories:** "ai story video generator" 2,900 against "bedtime story video" 390;
   - **YouTube:** "ai video generator for youtube" 4,400, up 4× in a year;
   - **caricature:** "ai caricature" 5,400.

   Creators already think in AI tools.
3. **What "ai" is growing on, and what it is falling on.**
   - Rising:
     - "ai birthday invitation", up 3.3× in a year;
     - "ai real estate video", up 1.9×;
     - "ai wedding video", up 1.7×;
     - "ai birthday video", up 1.6×;
     - "ai listing video", new since March 2026.
   - Falling: photo-animation searches ("ai talking photo", "ai photo to cartoon", "ai animate photo", all 0.4×) and "ai training video generator" (0.5×). Training buyers may be finding vendors by name now (synthesia 368k, heygen 1.5M).

   AI for a specific job is rising; the photo-trick fad is fading.
4. **"ai" is where B2B advertisers pay most:**
   - ai training video generator: $35.49
   - ai ad creator: $21.66
   - ai listing video: $16.18
   - ai ad maker: $15.59

   Volumes are small, but these are buyers who already decided to use AI.
5. **"Template" searches are consumer and editor searches.**
   - Volume sits in occasions and YouTube:
     - wedding invitation video templates: 5,400, plus 9,900 "…free download";
     - birthday video templates: 2,900;
     - youtube video templates: 2,400;
     - youtube shorts and intro templates: 1,600 each.
   - Business templates are close to zero: onboarding 20, recruitment 10, product demo 40,
     explainer 210. The exceptions are testimonial (260, $12.78 bid) and church announcement (390).
   - Many template searchers want an editable file: after effects templates 14,800, premiere pro
     templates 4,400, motion graphics templates 6,600, and "free download" variants everywhere.
     A remake-by-prompt template has to say so on the page: no software, no download, the film
     is made for you.
6. **Events are searched for by the job, not as a template.** "Speaker announcement" gets 3,600 and
   "call for speakers" 2,400, but their "template" versions get 10–30. Name event pages after the job.
7. **Training templates are tiny but growing fastest:** 170 a month, up 5.8×. Worth a page now.

**How to name pages:**
- **Template gallery index:** target "video templates" (40,500, growing) and "AI video templates"
  (880, growing). Both describe exactly what the gallery is.
- **Occasion pages:** the plain job phrase, then "template" and "maker". For example: "Wedding
  invitation video: a template made from your photos, by AI".
- **Creator pages:** lead with "AI": "AI story video generator", "AI video generator for YouTube".
- **Business pages:** the plain job phrase. These pages serve ads (high bids) more than organic
  search; use the "ai … generator" form for paid search.

## 2. HeyGen: who it sells to, and where we meet it

**Scale:**
- Revenue run-rate:
  - $1M (2023-04);
  - $100M (2025-10) **[own claim, Joshua Xu on X]**;
  - $200M (2026-06, Upstarts from company figures; Sacra estimates $205M).
- Cash-flow break-even in 2026, with $25M of the $74M raised spent (Upstarts).
- **[own claim]** 30M users, 120M+ videos, "85% of the Fortune 100". Its own enterprise page says
  80%, so its figures disagree.

**Who it targets** (heygen.com, read live on 2026-10-02):
- **Homepage tabs:** Social Content, Online Courses, Legal, Finance, Real Estate.
- **Teams:** Marketing, L&D, Sales, Customer Success, Product Marketing, Internal Communications,
  Compliance Training, Agencies.
- **Industries (/enterprise):** Pharma, Healthcare, Real Estate, Legal, Fintech, Retail,
  Manufacturing, Education, Hospitality, Insurance.
- **36 use-case pages** (sitemap): learning-courses, ai-tutorials, ai-video-ads, ai-sdrs,
  event-marketing, how-to-videos, corporate-training, sales-outreach, webinars-and-podcasts,
  religious-content, language-learning, product-explainers, onboarding-training, newsletters-and-community,
  news-stories, documentary-style, keynotes, product-announcements, safety-training, personal-greetings,
  financial-knowledge-sharing, compliance-training, customer-stories-and-testimonials, motivational-content,
  historical-storytelling, medical-knowledge-sharing, fortune-telling, and others.
- **~130 SEO tool pages**, including ai-cartoon-video-maker, faceless-video, patient-education-videos,
  infographic-video-maker, and holiday, wedding, memorial and baby-announcement makers.
- **Its first profession-specific product: HeyGen for Real Estate** (2026-08-11). It covers
  listing videos, market updates, new construction and virtual staging, with a done-for-you service.
- **About 29 certified agencies** listed.

**Who actually pays:**
- **Small businesses** (Upstarts). G2 rated it a Leader for small-business AI video, fall 2026.
  The 72 customer stories are mostly small businesses:
  - about 15 realtors and mortgage brokers;
  - clinics;
  - course creators.
- **Enterprises**, for localization and training: Workday, Coursera, Miro, Komatsu, Würth, Lattice,
  HubSpot, Trivago, Rosetta Stone.

**Pricing:**

| Plan | Price | What it adds |
|---|---|---|
| Free | $0 | 3 videos a month |
| Creator | $29 a month ($24 billed yearly) | 600 credits |
| Pro | from $49 | — |
| Business | $149 a month + $20 a seat | SSO, LMS/SCORM, 5 custom avatars |
| Enterprise | custom | — |

- The newest avatar burns 20–48 credits a minute, so Creator buys roughly 12–30 minutes of it.
- Legacy "unlimited" plans closed to new customers on 2026-05-15.

**Its weak spots:**
- **Looking fake:** 50.7% of non-users worry about it, and 64.6% say trust needs authenticity.
  Both figures are from HeyGen's own survey.
- **Credit burn, including on failed renders.** Trustpilot is now 4.0 from 4,016 reviews, 15%
  one-star. It was 2.4 earlier in 2026.
- **Stuck renders, a support bot, hard refunds.**
- **Counter-evidence:** a Bochum study (n≈500, 2025) found realistic avatars trusted *more* than
  cartoon ones. Our opening is cost, sameness, and content that needs no presenter, not
  "drawn always wins".

**Where an animated film is a credible or better substitute for HeyGen:**
1. **Compliance, safety and SOP training.** A drawn scene can show the hazard; an avatar can only
   talk about it.
2. **Product and SaaS explainers.** The content is screens, flows and logos, not a face. This is
   the head-on fight with HyperFrames.
3. **Patient and HCP education.** Anatomy needs drawing, and there is no synthetic doctor.
4. **Finance, legal and insurance concepts.** A diagram, and no "is this a real advisor?" in a
   regulated industry.
5. **History, documentary, news and faith storytelling.**
6. **Faceless channels.** A distinctive look beats the stock avatars every other channel uses.
7. **Kids and language learning.**
8. **Localizing new content.** There is no lip-sync to fake. This is not dubbing real footage.
9. **The 50.7% who are "worried about looking fake".** Draw the person.
10. **Events, line-ups, recaps, greetings and memorials.**
11. **Leadership updates and onboarding.** A drawn CEO, not a deepfake one. It cannot personalise
    each of 100,000 copies, which is HeyGen's strength.

**Not substitutes:** UGC ads, AI SDRs, live avatars, dubbing real people, and personalised outreach
to each recipient.

**Synthesia and Colossyan** sell almost only to enterprise L&D:
- Synthesia has $146M a year in revenue and 65k customers, 70% of revenue from enterprise
  (Sacra, 2025-09). It raised $200M at a $4B valuation in 2026-01.
- HeyGen is the one of the three that also owns small business, creators and marketing.

## 3. What 13 animated and template tools cover

How many of the 13 name each niche:

| Niche | Tools |
|---|---|
| Marketing / promo | 13 |
| Education | 13 |
| Training / L&D | 11 |
| Social formats | 11 |
| Explainer | 10 |
| Infographic / data | 10 |
| Events / invitations / webinars | 9 |
| HR / recruiting / onboarding | 9 |
| Greetings / birthday / wedding | 8 |
| Presentations | 8 |
| Intros / logos | 8 |
| Sales / demo | 8 |
| Internal comms | 7 |
| Real estate | 7 |
| Healthcare | 6 |
| Compliance / safety | 6 |
| News / thought leadership | 6 |
| Food / hospitality / travel | 6 |
| Professional services | 5 |
| Tech / IT | 5 |
| Finance / insurance | 4 |
| Customer support / FAQ | 4 |
| Year in review | 4 |
| Retail | 4 |
| Government | 3 |
| Nonprofit | 3 |
| Pitch deck | 3 |
| Kids / cartoon story | 3 |
| Fitness / sports | 3 |
| DEI | 2 |
| Automotive | 2 |
| Manufacturing / logistics | 2 |
| Maps | 1 |
| Conference speakers / agenda / call for speakers | 0 |

**Where they invest.** The navigation (where they invest) carries:
- training/L&D, HR, internal comms, marketing and sales;
- a short list of 7–8 industries (Vyond: Finance, Government, Healthcare, Hospitality, Pharma,
  Professional Services, Software & Tech).

Consumer niches (weddings, pets, holidays) sit in long lists.

**What gets used.** Only Renderforest publishes per-template use (exports):

| Template | Exports |
|---|---:|
| Solid Logo Reveal | 4M+ |
| Event Promo Story | 349K |
| Business Presentation Pack | 294K |
| Company Year-In-Review | 294K |
| Cyber Security Conference Promo | 281K |
| Animated FAQ | 103K |
| Infographics Animation Pack | 95K |
| Conference Event Opener | 72K |
| World Map Video Toolkit | 40K |

**Price anchors** (per month unless stated):

| Tool | Price |
|---|---|
| Vyond | $58–100, or $699–1,999 per user per year |
| Powtoon | $15–125 (premium templates from $40) |
| Animaker | $10–49 |
| Renderforest | $9–59 |
| Biteable | $15–49 |
| Pictory | $25–119 |
| Canva Pro | $144 a year |

Industry templates are almost never paywalled as such. The upsell is brand kits, seats, watermark
control, resale rights and credits.

## 4. Who pays, how often, and how much

**Freelance and agency prices:**
- **Fiverr:**
  - "Animated Explainers" has ~12,000 services.
  - Real 60 s explainers sell for $500–3,000; healthcare 2D starts at $3,250.
  - Searches for "faceless YouTube video creator" rose **488%** (Fiverr Business Trends Index,
    2025-12). "AI UGC video ads" rose 265% (2026-06).
- **Upwork:**
  - 869 open whiteboard jobs.
  - Recurring buyers include finance channels (8–10 videos a month), an engineering channel
    (1–2 a week), a stick-figure channel ($40–50 a video, 2–3 a week), a 1.6M-subscriber tech
    channel, and a recruitment-agency studio.
- **Agencies:** a 60 s animated explainer has a median price of $5,400 and a mean of $10,983
  (Wyzowl survey of 242 studios). Breadnbeyond charges $4.3–20k, Epipheo $5–75k, Demo Duck $16k+.
  - Every agency features financial services, healthcare, SaaS and education.
  - HR, insurance, nonprofit, legal and real estate recur.

**Surveys:**
- **Wyzowl 2026** (n=266):
  - 91% of businesses use video, and 68% have made an explainer.
  - Live action is the main style for 51%, animation for 23%.
  - Of those not using video, 24% say it is too expensive and 19% say they lack the time.
- **Animoto 2026:** 36% of consumers say an AI video lowers their view of the brand. The giveaways
  are "robotic gestures" (67%) and voices (55%).
- **Gartner (2025-10):** 50% of consumers prefer brands that avoid generative AI in what they show
  customers.

**Segments that already pay for ready-made video, and how often they need one:**

| Segment | Size | How often | They pay today |
|---|---|---|---|
| Corporate L&D, compliance, onboarding | US training spend $102.8B, of which $16B is outside products (Training mag., 2025) | a third of small L&D teams make 21+ videos a month **[HeyGen report]** | Synthesia, Vyond and HeyGen seats |
| Financial advisors | 326k in the US (BLS) | weekly or monthly | FMG: $209–289 a month for a reviewed library of 400+ videos and articles; Broadridge's video studio |
| Medical and dental practices | ViewMedica: 2,572 videos | continuous | $1,020–4,500 a year for animated patient-education libraries |
| Real-estate agents | NAR ~1.4M; 24% spend $500+ a month on tech | monthly | Coffee & Contracts: done-for-you templates at $45–54 a month, a $1M-a-year business |
| HR benefits | Jellyvision ALEX: 18M employees | yearly enrollment plus life events | enterprise SaaS |
| Course creators | Kajabi 100k, Teachable 200k | per module | proven buyers of tools |
| Teachers | 76.5% of US teachers use YouTube in class | weekly | BrainPOP $99 a year per family plus school licences |
| Nonprofits | 1.54M 501(c)(3)s | per campaign | ThankView $3–6k a year |
| Churches | ~357k congregations | weekly | Church Motion Graphics $249 a year |
| Faceless channels | Fiverr searches +488% | 2–3 a week | $40–100 a video to freelancers |
| Newsletter writers | Substack: 50k paid publications | weekly | writers using audio or video grew revenue 50% faster (Sacra) |
| Law firms | only ~30% make video | monthly | high bids ($48–55 a click) |
| Municipalities | 90,837 US local governments | yearly (budget, elections) | LA County and Dallas animate their budgets, in English and Spanish |

**Why animation, with evidence:**
- **Health:** across 88 randomised trials, 80% reported knowledge gains from animation over usual
  care (systematic review, 2026-01).
- **Learning:** whiteboard animation beat slides, lecture, audio and text on retention (Türkay 2016,
  n=568).
- **Languages:** animation is the cheapest to re-voice in another language, because there is no
  lip-sync or reshoot.

## 5. What has been made on kitcut.ai so far

These are the 187 web films to 2026-10-02, read by topic only through `prod.mjs`. The films include
ours and users', and they could not be separated without reading account details.

The biggest groups:
- kids' bedtime stories and kids' series (Leo, Duchess, Pip, Olga);
- kids' science and kids' economics in Ukrainian;
- conference films;
- small-business promos (a restaurant, a wine shop, a bakery);
- money explainers (compound interest, buying the dip, trading concepts);
- course lessons (sailing knots in Spanish, German grammar);
- history and business documentaries;
- product launches.

That matches the Habit and Reach portfolios below.

## 6. The catalogue: 154 new templates

**Columns:**
- **Often:** how often one buyer needs another (W weekly, M monthly, Q quarterly, Y yearly,
  E per event, 1 once).
- **Edge:** what KitCut does that an avatar tool or a stock template cannot.
- **Wave:** 1 is the first 30 (see section 7), 2 the next, 3 later.

Every template should launch with **one real, specific example film**: a real company, event or
place, with real logos and real numbers ([[films-be-specific]] in the memory). The example is what
a person remakes.

Live already: conference speaker promo, conference in numbers, conference agenda, call for
speakers, ride replay.

### A. Events and conferences (11)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| A1 | Sponsor showcase and thank-you | organisers | E | logo wall, cut-outs | 2 |
| A2 | Countdown teaser (7, 3, 1 days to go) | organisers | E×3 | reuses the speaker cut-outs | 2 |
| A3 | Getting there: venue, transit, hotels on a map | organisers | E | route tool | 2 |
| A4 | Meetup or community-night announcement | community leads | M | people cut-outs | 2 |
| A5 | Hackathon: theme, prizes, rules, then the winners | organisers | E | numbers, cut-outs | 2 |
| A6 | Awards: nominees, then winners reveal | associations | Y | cut-outs, reveal | 2 |
| A7 | Webinar or workshop promo | B2B marketers | M | speaker drawn from photo | 2 |
| A8 | Early-bird deadline / last tickets | organisers | E×3 | numbers, countdown | 2 |
| A9 | Thank-you recap from the day's photos | organisers | E | collage from photos | 2 |
| A10 | Trade-show booth invite ("find us at stand 214") | exhibitors | E | floor map | 3 |
| A11 | Festival line-up reveal | festival promoters | Y | collage, music | 3 |

### B. Personal occasions (12)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| B1 | Kid's birthday party invitation | parents | Y | the child drawn, map to the venue | **1** |
| B2 | Wedding invitation / save the date | couples | 1 | the couple drawn, map, RSVP card | **1** |
| B3 | Our story: how we met, as a timeline | couples | Y | map of places, drawn couple | 2 |
| B4 | Baby announcement / gender reveal | parents | 1 | gentle drawn style | 2 |
| B5 | Baby or bridal shower invitation | friends | 1 | — | 3 |
| B6 | Graduation tribute | families, schools | Y | photo collage | 2 |
| B7 | Retirement or farewell tribute for a colleague | teams | ad hoc | photos drawn, career timeline | **1** |
| B8 | Celebration of life / memorial | families | 1 | painted look, photo → portrait | **1** |
| B9 | Family year in review (holiday card) | families | Y (Dec) | map of trips, drawn family | **1** |
| B10 | Thank-you film (teacher, coach, guests) | anyone | ad hoc | drawn people | **1** |
| B11 | We moved / housewarming, with a map | families | 1 | route tool | 3 |
| B12 | Pet's birthday or adoption story | pet owners | Y | pet drawn from photo | 3 |

### C. Kids and family (10)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| C1 | Bedtime story (calm, 2–3 min) | parents, kids' channels | W | crayon/painted, gentle voice | **1** |
| C2 | Episode of a kids' series with a recurring character | kids' channels | W | series library keeps characters and places | **1** |
| C3 | "Why does…?" science for kids | kids' channels, teachers | W | diagrams a 5-year-old follows | **1** |
| C4 | Social story: a new routine (potty, daycare, doctor) | parents, therapists | ad hoc | the child as the hero | **1** |
| C5 | Sing-along nursery rhyme | toddlers' channels | W | score and lyrics on screen | 3 |
| C6 | Fable retold | kids' channels, teachers | W | painted look | 2 |
| C7 | Counting / alphabet / colours | toddlers' channels | W | — | 2 |
| C8 | Money for kids (an economics series) | kids' channels, schools | W | collage, numbers | 2 |
| C9 | Holiday story (Halloween, Christmas, Diwali, Lunar New Year) | parents, schools | Y | seasonal | 2 |
| C10 | Your child as the hero of the story | parents | ad hoc | the child drawn from a photo | 2 |

### D. Faceless channels and creators (13)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| D1 | History documentary episode | channels | W | painted look, maps | **1** |
| D2 | How it works: a machine, system or process | channels | W | diagrams | **1** |
| D3 | Business story: how a company rose or fell | channels | W | real logos, charts | **1** |
| D4 | Tech or AI news explained | channels, newsletters | W | logos, timelines | 2 |
| D5 | Top-N facts (vertical Short) | channels | daily | 9:16 | 2 |
| D6 | A book in three ideas | channels | W | — | 2 |
| D7 | Biography / true story | channels | W | person drawn from a public photo | 2 |
| D8 | Map story: an empire, a voyage, a supply chain | channels | W | route tool | 2 |
| D9 | Versus: two companies, two products | channels | W | charts, logos | 2 |
| D10 | Personal finance for a channel | channels | W | charts | 2 |
| D11 | Science myth-busting | channels | W | — | 3 |
| D12 | Cinematic micro-fiction (a sci-fi short, the last penalty) | storytellers | W | painted look | 3 |
| D13 | Indie game or app trailer | indie developers | E | screens, logo | 2 |

Note: channels often want 8–12 minute episodes. Our sweet spot is 30–120 s; a long film costs
hours (see `docs/studio-speed.md`). Lead with Shorts and 2–3 minute formats.

### E. Teachers, tutors and course makers (10)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| E1 | One concept in 90 seconds | teachers, tutors | W | any subject, any language | **1** |
| E2 | Language micro-lesson (one grammar point) | language teachers, apps | W | voice in the target language | **1** |
| E3 | A skill in steps (a knot, a repair, a recipe) | instructors | W | numbered steps | 2 |
| E4 | Course trailer | course creators | E | — | 2 |
| E5 | Module intro / recap | course creators | per module | — | 2 |
| E6 | Exam-prep summary | tutors | seasonal | — | 2 |
| E7 | A historical event, for class, with a map | teachers | W | route tool | 2 |
| E8 | A cycle or process (water cycle, photosynthesis) | teachers | W | diagrams | 2 |
| E9 | School announcement / open day / back to school | schools | M | — | 2 |
| E10 | University programme promo | universities | Y | — | 3 |

### F. Workplace training and compliance (10)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| F1 | Safety: spot the hazard (warehouse, site, kitchen) | EHS managers | M | the scene is drawn and acted, not described | **1** |
| F2 | Policy explainer (harassment, conduct) | HR, compliance | Y + every hire | scenarios with drawn people | **1** |
| F3 | Cyber-security: spot the phish | IT, security | M | screens, red flags | **1** |
| F4 | Standard procedure in steps | operations | ad hoc | numbered steps | 2 |
| F5 | New tool rollout ("we're moving to X") | IT, operations | E | screens, logos | 2 |
| F6 | Customer-service scene, done badly then well | support leads | M | two-take scenario | 2 |
| F7 | Sales training: handling an objection | sales enablement | M | dialogue | 2 |
| F8 | Microlearning recap with a quiz question | L&D | W | — | 2 |
| F9 | Data privacy basics | compliance | Y | — | 3 |
| F10 | Equipment basics (forklift, PPE) | EHS | Y | — | 3 |

Note: selling to L&D needs LMS/SCORM export, brand kits and seats. HeyGen ships SCORM on its $149
Business plan; we have none of these yet.

### G. HR and internal comms (8)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| G1 | Welcome to the team (first day) | HR | every hire | the team drawn from photos | **1** |
| G2 | Benefits open enrollment explained | HR | Y (Oct–Nov) | diagrams; **in season now** | **1** |
| G3 | CEO's quarterly update | comms, leadership | Q | CEO drawn from a photo, charts | **1** |
| G4 | Company year in review / in numbers | comms | Y (Dec) | numbers (reuses conference-in-numbers) | **1** |
| G5 | Job ad: a day in the role | recruiters, staffing agencies | W | the team drawn | 2 |
| G6 | Values and culture | HR | Y | — | 3 |
| G7 | Policy change announcement | HR | ad hoc | — | 2 |
| G8 | Work anniversary / team milestone | team leads | M | photo → drawn | 2 |

### H. SaaS and tech (11)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| H1 | Product explainer: problem, then solution | founders, product marketers | E | screens, logos | **1** |
| H2 | Feature launch | product marketers | M | screens | 2 |
| H3 | Monthly release notes / changelog | product teams | M | a list read from the changelog | **1** |
| H4 | How it works for developers (architecture, API) | devrel | E | dark, precise ([[kitcut-films-for-developers]]) | 2 |
| H5 | Integration announcement (X + Y) | partnerships | M | logos | 2 |
| H6 | Customer case study, before and after in numbers | marketing | M | charts, customer logo | 2 |
| H7 | Funding or milestone announcement | founders | Y | numbers | 2 |
| H8 | Get started: the first three steps | growth teams | per release | screens | 2 |
| H9 | Pricing or plan change explained | product | ad hoc | — | 3 |
| H10 | Demo-day pitch in 90 seconds | startups | per round | — | 2 |
| H11 | How we keep your data safe (SOC 2, encryption) | B2B SaaS | Y | diagrams | 3 |

### I. Small and local business (8)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| I1 | Our story: the place, the people, the craft | restaurants, shops, makers | 1 + seasonal | owners drawn, painted look | 2 |
| I2 | New arrival / new product in store | shops | M | product drawn from photo | 2 |
| I3 | Seasonal promo / holiday sale | shops | M | — | 2 |
| I4 | Grand opening / new location, with a map | any local business | 1 | route tool | 2 |
| I5 | How we make it (bakery, roastery, brewery) | makers | 1 | steps | 2 |
| I6 | What to expect at your first visit (salon, gym, clinic) | services | 1 | — | 2 |
| I7 | A customer review brought to life | any | M | — | 3 |
| I8 | This week's specials | cafés, restaurants | W | — | 2 |

### J. Real estate and home (7)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| J1 | Monthly market update | agents | M | charts from the numbers they paste | **1** |
| J2 | Neighbourhood guide | agents | per area | map, places | 2 |
| J3 | How buying a home works | agents, lenders | evergreen | steps | 2 |
| J4 | How selling works / pricing your home | agents | evergreen | — | 2 |
| J5 | Just listed / just sold | agents | W | collage from listing photos | 2 |
| J6 | Mortgage rates: lock or float this week | brokers | W | charts | 2 |
| J7 | What you can build on your lot (ADU, zoning) | architects, builders | evergreen | diagrams | 3 |

### K. Finance, insurance and advisors (8)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| K1 | Weekly market recap | advisors, newsletters | W | charts, no fake advisor | **1** |
| K2 | A money concept (compound interest, diversification) | advisors, channels | W | diagrams | 2 |
| K3 | Tax season explained | accountants | Y | — | 2 |
| K4 | What your policy covers | insurance agents, brokers | evergreen | diagrams | 2 |
| K5 | How a claim works | insurers | evergreen | steps | 2 |
| K6 | Retirement planning basics | advisors | evergreen | — | 2 |
| K7 | Fintech product explainer | fintechs | E | screens | 2 |
| K8 | A trading concept | trading educators | W | charts | 3 |

Note: advisors need compliance review (FINRA in the US). Build the films so the wording can be
signed off before rendering.

### L. Healthcare and wellness (9)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| L1 | A procedure explained (dental implant, knee scope) | clinics | continuous | drawn anatomy; animation's proven case | **1** |
| L2 | A condition explained | clinics, health channels | continuous | — | 2 |
| L3 | Before and after your visit | clinics | evergreen | steps | 2 |
| L4 | New clinic or new service | clinics | E | — | 2 |
| L5 | How to use your medication (inhaler, injector) | pharmacies | evergreen | — | 3 |
| L6 | A gentle mental-health explainer | therapists, apps | W | soft look | 2 |
| L7 | Pet care explained | vets | evergreen | — | 3 |
| L8 | Public-health campaign (screening, vaccines) | health agencies | E | many languages | 3 |
| L9 | A nutrition or fitness idea | trainers, dietitians | W | — | 2 |

Note: medical accuracy is a real risk. Ship with a review step, and claim education only, never
advice.

### M. Legal and professional services (5)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| M1 | What to do after… (a car accident, a layoff) | law firms | M | steps | 2 |
| M2 | The process on a timeline (divorce, immigration, probate) | law firms | evergreen | timeline | 2 |
| M3 | Know your rights | firms, NGOs | evergreen | many languages | 2 |
| M4 | Meet the firm, with the partners drawn | firms | 1 | cut-outs | 3 |
| M5 | A client question answered | accountants, consultants | M | — | 3 |

### N. Nonprofits and public sector (7)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| N1 | Fundraising appeal: one person's story | nonprofits | per campaign | painted look, numbers | 2 |
| N2 | Impact report in numbers | nonprofits | Y | numbers | 2 |
| N3 | Donor thank-you | nonprofits | per campaign | — | 2 |
| N4 | Volunteer call | nonprofits | E | — | 3 |
| N5 | The city budget explained | municipalities | Y | charts, two languages | 3 |
| N6 | How to vote (where, when, what to bring) | election offices, media | E | map | 3 |
| N7 | Public service announcement | agencies | E | — | 3 |

### O. Faith communities (4)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| O1 | This week at church (announcements) | churches | W | — | 2 |
| O2 | Sermon recap / illustration | churches | W | painted look | 2 |
| O3 | Bible story for kids | churches, Sunday schools | W | kids' look | 2 |
| O4 | Easter / Christmas service invitation | churches | Y | map | 2 |

### P. Media, newsletters and podcasts (5)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| P1 | This week's newsletter as a film | writers | W | made from the text they paste | **1** |
| P2 | Why it happened (news explainer) | media, channels | daily | timeline, logos | 2 |
| P3 | Podcast episode in 60 seconds | podcasters | W | — | 2 |
| P4 | The week's top five | media, communities | W | — | 2 |
| P5 | Book trailer | authors | E | painted look | 2 |

### Q. Travel, sport and the outdoors (5)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| Q1 | Our trip on a map | travellers, tour agencies | E | route tool | **1** |
| Q2 | Club season in numbers | sports clubs | Y | numbers, crest | 2 |
| Q3 | The match / the race, told as a story | clubs, fans | W | painted look | 3 |
| Q4 | A route guide (hike, wine route, city walk) | tour operators | evergreen | route tool | 2 |
| Q5 | Race-course preview (marathon, gran fondo) | race organisers | Y | GPX → map | 2 |

### R. Reports and data stories (4)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| R1 | Survey results | marketers, researchers | E | charts | 2 |
| R2 | Quarterly results / investor update | companies | Q | charts | 2 |
| R3 | Annual report highlights | companies, nonprofits | Y | numbers | 2 |
| R4 | Our history as a timeline | companies | 1 | timeline | 3 |

### S. Me, drawn (4)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| S1 | Introduce yourself: you, drawn from your photo, talking | coaches, consultants, job seekers | 1 | the answer to "worried about looking fake" | **1** |
| S2 | A LinkedIn post as a film | professionals | W | — | 2 |
| S3 | Speaker or expert bio | speakers | E | — | 3 |
| S4 | The agent's or advisor's own channel intro | realtors, advisors | 1 | drawn, not avatar | 2 |

### T. E-commerce and ads (3)
| # | Template | For | Often | Edge | Wave |
|---|---|---|---|---|---|
| T1 | A 15-second animated product ad | DTC brands | W | product drawn from photo | 2 |
| T2 | How to use it | brands | E | steps | 3 |
| T3 | Product-drop teaser | brands | E | — | 3 |

UGC-style ads are deliberately absent: they are HeyGen's (1,100+ creator avatars).

## 7. The first 30, as three portfolios

| Portfolio | Why | Templates | Scored by |
|---|---|---|---|
| **Habit:** weekly formats | 0 people had returned on another day by day 5; a series is a reason to come back | C1 bedtime story, C2 kids' series episode, C3 why-science for kids, D1 history episode, D2 how it works, D3 business story, E1 concept in 90 s, E2 language micro-lesson, K1 weekly market recap, P1 newsletter as a film | second film within 14 days |
| **Revenue:** people already paying for ready-made video | budgets exist: L&D seats, $209–289/mo advisor libraries, $1–4.5k/yr patient-education libraries, $45–54/mo realtor templates | F1 spot the hazard, F2 policy explainer, F3 spot the phish, G1 welcome to the team, G2 open enrollment (in season), G3 CEO quarterly update, H1 product explainer, H3 monthly release notes, J1 monthly market update, L1 procedure explainer | paid plans opened from a template |
| **Reach:** occasions and "maker" searches | 27k/mo wedding-invitation and 12k birthday searches; every guest sees the film | B1 kid's birthday invite, B2 wedding invite / save the date, B7 retirement / farewell, B8 memorial, B9 family year in review, B10 thank-you, C4 social story (potty: 3.6k/mo), G4 company year in review, Q1 our trip on a map, S1 introduce yourself, drawn | sign-ups from template pages and from films' viewers |

**Search pages.** For reach, pair each template with a page aimed at its head phrase ("wedding
invitation video", "turn photo into cartoon"). This is HeyGen's /tool/ play, but with one real
film per page, never near-duplicates.

**Seasonal templates first.** Build open enrollment (G2), the Halloween story (C9) and the year in
review (B9, G4) before their peaks.

## Sources

**Search demand:** Google Ads Keyword Planner, customer 5439691191, queried 2026-10-02.

**HeyGen:**
- [heygen.com](https://www.heygen.com/), [business](https://www.heygen.com/business),
  [enterprise](https://www.heygen.com/enterprise), [sitemap](https://www.heygen.com/sitemap.xml),
  [pricing](https://www.heygen.com/pricing), [real estate](https://www.heygen.com/blog/introducing-heygen-for-real-estate),
  [July 2026 release](https://www.heygen.com/blog/heygen-july-2026-release),
  [State of AI avatars 2026](https://www.heygen.com/the-state-of-ai-avatars-2026),
  [HyperFrames](https://github.com/heygen-com/hyperframes).
- Third parties: [Upstarts on $200M ARR](https://www.upstartsmedia.com/p/exclusive-heygen-200m-arr-without-burn),
  [Sacra](https://sacra.com/c/heygen), [Ramp](https://ramp.com/vendors/heygen),
  [Trustpilot](https://www.trustpilot.com/review/heygen.com).

**Competitor catalogues:**
[Vyond](https://www.vyond.com/templates/), [Powtoon](https://www.powtoon.com/video-templates),
[VideoScribe](https://www.videoscribe.co/en/templates/), [Animaker](https://www.animaker.com/templates),
[Renderforest](https://www.renderforest.com/templates), [Biteable](https://biteable.com/templates/),
[Moovly](https://www.moovly.com/), [Steve.ai](https://www.steve.ai/templates), [InVideo](https://invideo.io/templates/),
[Pictory](https://pictory.ai/templates), [Lumen5](https://lumen5.com/templates/).

**Who pays:**
- Agency prices: [Wyzowl explainer cost](https://www.wyzowl.com/how-much-does-an-explainer-video-cost/),
  [Breadnbeyond](https://breadnbeyond.com/pricing), [Epipheo](https://epipheo.com/explainer-video-cost/).
- Training: [Training mag. 2025](https://trainingmag.com/2025-training-industry-report/),
  [Synthesia on Sacra](https://sacra.com/c/synthesia).
- Healthcare and advisors: [ViewMedica pricing](https://viewmedica.com/integrated-patient-education-videos/pricing/),
  [FMG](https://fmgsuite.com/ufc/).
- Real estate: [Coffee & Contracts](https://www.starterstory.com/stories/i-created-a-1m-year-subscription-based-toolkit-for-real-estate-professionals),
  [NAR 2025](https://www.nar.realtor/newsroom/realtors-embrace-ai-digital-tools-to-enhance-client-service-nar-survey-finds).
- Freelancers: [Fiverr trends](https://www.fiverr.com/news/2025-fall-business-trends-index),
  [Upwork whiteboard jobs](https://www.upwork.com/freelance-jobs/whiteboard-animation/).
- Consumers on AI video: [Animoto 2026](https://www.businesswire.com/news/home/20260121875037/en/83-of-Consumers-Can-Spot-AI-Videos-36-Say-It-Lowers-Brand-Trust-According-to-Animotos-New-Report).

**Why animation:**
[88-trial review](https://pmc.ncbi.nlm.nih.gov/articles/PMC12808424/),
[Türkay 2016](https://www.vpal.harvard.edu/publications/educational-impact-whiteboard-animations-experiment-using-popular-social-science).
