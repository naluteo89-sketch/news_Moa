**English** | [한국어](README.md)

# news_Moa · News Analysis

A web service that collects Naver News search results and instantly shows each article's **positive/negative tone**, **key keywords**, and **key sentences**.
Per-article analysis is done in Python (sentiment lexicon, morphological analysis); only the **"Page mood"** panel on the right uses an **LLM (OpenAI `gpt-6-luna`)**, with one call per page.
Unlike existing news analytics services that focus on search volume and mention counts, it is designed to help you **quickly understand "what is actually being said" while reading the articles themselves**.

![Main screen](docs/screen_main.jpg)

![Expanded article](docs/screen_article.jpg)

---

## Why This Project

Reading the news, you often run into these problems:

1. **Headlines that don't match the article**: a sensational headline over an ordinary story, or a headline that says little about the content.
2. **No way to see the tone at a glance**: you have to open each article to know whether it is positive, negative, or a neutral factual report.
3. **A flood of articles all leaning the same way**: when negative (or positive) stories about one topic appear all at once, readers wonder whether outlets are coordinating their tone, but there is no easy way to check.
4. **Comments driven by the headline alone**: the topic and content are fine, yet off-target or hostile comments pile up from people who only read the headline.

news_Moa was planned to **help readers judge articles by their content**. If readers check the actual content and tone before the headline, comments born of misunderstanding should decrease.

| Problem | Feature |
|---|---|
| Headline vs. content mismatch | **Key sentences**: body sentences ranked by overlap with the headline and subheadline, with match rates (headline %, subheadline %). Few matching sentences is a sign the headline and body diverge. Click to jump to the sentence |
| Tone not visible at a glance | **Positive (blue) / negative (red) / neutral (gray)** badges and edge strips on every card, plus the words behind the verdict |
| Same-direction articles all at once | The **Page mood** panel (AI verdict) shows the positive/negative/neutral split at once; **publisher filters**, **date dividers**, and sort-by-date let you compare which outlet published what tone, and when |
| Comments based only on the headline | Articles expand right on the page so readers see the **body, key sentences, and tone first** |

> It does not decide whether collusion happened. The reader judges; the service quickly gathers the distribution and evidence needed for that judgment.

---

## What Makes It Different

### 1. Sentiment analysis that shows its evidence, not just a number
Instead of only saying "65.9% positive", it shows the **sentiment words behind the decision**, so you can open the article and check right away whether the judgment holds.
Even in the list, every article carries a positive/negative/neutral badge and a colored strip on the card edge, so the mood of the page is readable just by scrolling.

### 2. Token-frugal LLM use: one call per page
The LLM is used only for the **"Page mood"** panel on the right. Sending every article body would mean 10 calls and tens of thousands of tokens for a 10-article page; instead this project
- sends only the **search result title + summary** (up to 300 characters per article), not the body,
- **batches the whole page into a single call**,
- asks the model for **only the article number and a positive ratio (integer)**,
- and stores each verdict so the same article is **never sent again** on other pages or repeat searches.

The positive/negative/neutral label is **decided by code, not by the model** (35–65% positive = neutral). The article card badges (lexicon) use the same rule.
Even in the list, every article carries a positive/negative/neutral badge and a colored strip on the card edge, so the mood of the page is readable just by scrolling.

### 3. Jump straight to the "key sentences" that match the headline
Sentences containing the most nouns from the headline and subheadline are ranked. Clicking one **scrolls the article box to that sentence and highlights it in yellow**, so even long articles can be read starting from the core paragraph.

### 4. Reading by "expanding the article body" instead of a blocked original page
The first plan was to show the original article in a popup (iframe), but a check script showed that many publishers block iframes (7 of 20). The design was changed so the server **extracts the body text, subheadline, and photos and expands them under the card**. Naver News body extraction succeeded 7/7; when extraction fails, the search summary is analyzed instead and the screen says so.

### 5. Stackable filters by word and publisher
Selecting a frequent word and a publisher together keeps only the matching articles (e.g., "contains ‘AI’ · Yonhap News · 2 articles") and highlights the word. Empty date dividers are hidden, and if nothing matches, a button to clear the filter is shown.

### 6. A screen for both first-time users and power users
- **5-step tutorial**: real screenshots side by side with explanations; once closed, it stays closed.
- **Expert mode**: the screen stays simple by default; turning the switch on adds a page-wide keyword map and an article time distribution.
- **Dark mode**: follows the OS theme and can be switched with a button. Cards and photos get white borders so they don't blend into the dark background.

### 7. A layout that doesn't break at any screen size
- When a side panel is taller than the window, it scrolls with the page and **sticks once its bottom reaches the bottom of the window**, so everything is visible without an inner scrollbar.
- Images are size-checked first: **icons and logos are skipped**, tall photos don't stretch cards, and small photos aren't upscaled into blur.
- Article box height, pinned searches, recent searches, theme, and expert mode are remembered in the browser.

---

## Features

### Search
- Article search via the Naver News Search API (10/20/50/100 results, by relevance or date). Changing the count or sort re-runs the search immediately
- The home screen starts with a default query (`축제`, "festival")
- Page navigation at the top and bottom (up to 1,000 results, the API limit)
- **Pinned searches**: pin frequent queries to the header, remove with ×, add the current query with `+`
- Recent search history (up to 8)

### Article List
- **Thumbnails** taken from the article pages and **publisher names** resolved from the original URL (about 70 outlets; otherwise the page's `og:site_name`)
- **Positive (blue) / negative (red) / neutral (gray) badges** and a colored strip on the right edge of each card (lexicon verdict)
- Date dividers such as **"Today · Mon, Oct 26 news"** wherever the date changes
- Clicking a **frequent word** or a **publisher** on the left shows only the matching articles (can be combined)

### Reading an Article
- Clicking an article expands its **body, subheadline, and photos** below it (most publishers block iframes, so the body is extracted directly)
- The article box scrolls internally and can be resized from its bottom corner; the size is remembered
- **Key sentences** on the left: sentences ranked by overlap with the headline and subheadline. Clicking one jumps to it in the body and highlights it
- **Article analysis** on the right: positive/negative donut chart (lexicon), the sentiment words used as evidence, and frequent words

### Page Overview
- **Page mood** (top right): number and share of positive/negative/neutral articles **as judged by AI (gpt-6-luna)**. Without a key, or if the call fails, the lexicon verdicts are shown instead and the panel says so. Clicking an article in the list jumps to it and expands it
- **Expert mode** switch: adds "Keywords at a Glance" (page-wide word size map) and "Article Time Distribution" (articles per date/time slot)

### Interface
- **Dark mode**: follows the OS theme; a header button cycles System → Dark → Light. In dark mode, cards and photos get white borders
- 5-step tutorial panel (remembered when closed, reopen with `? 사용법`)
- Side panels stick at the bottom when taller than the window (no inner scrollbars)
- Image size check: small images such as icons and logos are excluded, and tall photos don't change card height

---

## How the Analysis Works

| Item | Method |
|---|---|
| Page mood (AI) | OpenAI Responses API with the `gpt-6-luna` model. See "How the LLM Is Used" below |
| Positive / negative (lexicon) | Sums word polarity (-2 to 2) from the [KNU Korean Sentiment Lexicon](https://github.com/park1200656/KnuSentiLex). Negations such as `좋지 않다` ("not good") and `안 좋다` flip the polarity. Same rule as the AI (35–65% positive = neutral). Used for card badges and article analysis, and for the panel when the AI isn't available |
| Morphological analysis | Uses `kiwipiepy`. Where it can't be installed, falls back automatically to a simple analyzer that strips Korean particles |
| Key keywords | Noun frequency per article; for the whole page, ranked by how many articles contain the word. The search query itself is excluded |
| Key sentences | How many headline nouns a sentence contains (60%) + how many subheadline nouns it contains (40%) |
| Body extraction | The body area (`#dic_area`) for Naver News pages; `trafilatura` or a simple extractor for publisher pages. On failure, the search summary is analyzed and the screen shows a notice |

### How the LLM Is Used (`components/ai_analyzer.py`)

| Item | Design |
|---|---|
| Where it's used | Only the "Page mood" panel on the right (card badges and article analysis use the lexicon) |
| Role (persona) | "A positive/negative checker for news articles". Rates how positive each article is toward its main subject (company, person, policy, event): achievements and praise score high; conflict, accidents, and concerns score low; plain factual reports stay near 50 |
| Input | A list of `[number] title / summary` lines for the page (up to 300 characters each; the body is never sent) |
| Output format | JSON Schema in `strict` mode: only `[{i, positive}]` (no reasons or sentences generated) |
| Calls | **One per page** (up to 100 articles at once) |
| Label | Decided in code: above 65% positive → positive, below 35% → negative, otherwise neutral. Numbers that weren't requested are dropped; values are clamped to 0–100 |
| Cache | Each article's ratio is stored in `data/ai_cache.json`; already-judged articles are left out of the next call |
| Fallback | Without a key, or when a call fails, lexicon verdicts fill the panel and it says so. Articles the model skipped are filled from the lexicon. If the model doesn't support the reasoning option, it retries once without it |

---

## Structure

```txt
news_Moa/
  main.py                 Flask web server (pages + API)
  components/
    naver_news_search.py  Naver News Search API calls and result cleanup
    article_fetcher.py    Article body, subheadline, photos, publisher name (cached)
    ai_analyzer.py        LLM (gpt-6-luna) batch page-mood verdicts, result cache
    text_analyzer.py      Lexicon sentiment, keywords, key sentences, page keywords
    press.py              Original URL → publisher name
  templates/index.html    UI (HTML, CSS, and JS in one file)
  static/tutorial/        Tutorial images
  check_article_fetch.py  Script that checks whether bodies/photos can be fetched from API result links
  docs/                   README screenshots
```

| Endpoint | Description |
|---|---|
| `GET /` | Search page (`query`, `display`, `start`, `sort`) |
| `GET /api/news` | Search results as JSON |
| `GET /api/preview` | For the list: thumbnail candidates, publisher name, positive/negative verdict (lexicon) |
| `POST /api/page-mood` | AI page-mood verdicts (`items`: list of link, title, summary) |
| `GET /api/article` | Article body + analysis (paragraphs/sentences, sentiment, keywords, key sentences) |

---

## Getting Started

```bash
pip install -r requirements.txt
python main.py        # http://127.0.0.1:5000
```

- **API key**: kept out of the repository in `C:\keydata\naver.py`. For another location, set the `NAVER_KEY_FILE` environment variable.
  ```python
  CLIENT_ID = "Naver Developers Client ID"
  CLIENT_SECRET = "Client Secret"
  ```
- **OpenAI key** (AI page mood): put it in `C:\keydata\gpt_key.py`. Without it, only the lexicon is used.
  ```python
  open_Aikey = "sk-..."
  ```
  | Environment variable | Default | Description |
  |---|---|---|
  | `OPENAI_API_KEY` | - | Used instead of the key file |
  | `OPENAI_KEY_FILE` | `C:\keydata\gpt_key.py` | Key file location |
  | `OPENAI_MODEL` | `gpt-6-luna` | Model used for the verdict |
  | `NEWS_AI` | `1` | `0` turns the AI verdict off |
  | `FLASK_DEBUG` | - | Debug mode only when `1` |
- **Sentiment lexicon**: downloaded automatically to `data/SentiWord_info.json` on first run (publicly released for research; excluded from the repo via `.gitignore`).
- On Python versions where `kiwipiepy` can't be installed, the simple analyzer is used. You can see which one is active at the bottom right of the article analysis panel ("형태소 분석: simple/kiwipiepy").

---

## Verification Results

Results of checking 20 real API results with `check_article_fetch.py`.

| Item | Result |
|---|---|
| Share of Naver News links | 7/20 (35%) |
| Naver News body extraction | 7/7 succeeded |
| Publisher page body extraction | 15/20 succeeded |
| iframe (embedding the original page) blocked | 7/20 → chose to extract and expand the body directly |

---

## Problems Solved During Development

| Problem | Cause | Fix |
|---|---|---|
| Showing the original article in an overlay gave a blank screen | Publishers and Naver block iframes | The server extracts the body and expands it under the card |
| Tall photos stretched cards to 446px; small photos were upscaled and blurry | Thumbnail height followed the photo's ratio; the gallery always filled its frame | Thumbnails fill and crop their slot; body photos are never shown larger than their original size; images under 100×60 are excluded |
| `&quot;` and `<b>` showed up in titles | API responses include HTML entities and tags | Strip tags + `html.unescape` |
| Some publisher pages had garbled text | EUC-KR pages that don't declare their encoding | Detect the encoding from the content |
| Scrollbars appeared inside the side panels | The sticky panels had a max height | Removed the height limit; panels taller than the window stick at the bottom |
| Panel positions were off after zooming the page to 110% | The zoom factor wasn't applied to the window-height calculation | Read the zoom factor and correct the calculation |
| The center column went blank when filters matched nothing | No message for zero results | "No matching articles" message + clear button |
| The API key was in the code | Initial sample code | Read the key from a file outside the repository (`*_key.py` is also in `.gitignore`) |
| Article URLs could reach the internal network (SSRF) | Links were requested as-is | Only public IPs allowed, re-checked on every redirect, pages over 5MB rejected |
| Calling the LLM per article used too many tokens | One call per article + 1,800-character bodies + generated reasons and evidence | LLM only for the page-mood panel; titles + summaries batched into one call; output is numbers and ratios only; per-article cache |
| The positive/neutral boundary drifted between runs | The label itself was left to the model | The model returns only ratios; code applies the 35–65% rule |

---

## Next Steps

- A view of articles where the AI and lexicon disagree; a labeled sample for measuring accuracy
- Log actual token usage (input/output tokens per page)
- Group articles about the same event; compare tone across publishers
- Tutorial images for dark mode
- Review the Naver Search API terms (revised 2026.09, restricting AI use) — required before any commercial use
- Article photos and text are copyrighted: for personal analysis only
