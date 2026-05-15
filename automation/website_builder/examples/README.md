# Website Builder — Examples Directory

Drop your reference website files here. The builder will read them and use the
OpenAI API to generate unique, stylistically similar websites.

## What to put here

You can provide reference materials in two ways:

### 1. HTML files
Place `.html` files directly in this directory. The builder reads them,
extracts structure and style, and generates a new site inspired by them.

```
examples/
  landing-page.html
  pricing-page.html
```

### 2. URLs file
Create a file named `urls.txt` with one URL per line. The builder will fetch
each URL and use the content as a reference.

```
# examples/urls.txt
https://stripe.com
https://linear.app
https://vercel.com
```

### 3. Image screenshots
Place `.png` or `.jpg` screenshots of websites here if you want the builder to
replicate the visual layout (requires a vision-capable OpenAI model such as
`gpt-4o`).

## Notes

- Reference files are **read-only**. The builder never modifies them.
- Generated output is written to `website_builder/generated/<domain>/`.
- If this directory contains no files (only this README), the builder falls
  back to the default template at `website_builder/templates/base.html`.
