require "time"

# Renders the X mirror from the committed JSON in _data/x/: /x/ and /x/<year>/
# for humans, /llm/x.md and /llm/x/<year>.md for machines. The build needs no API
# access, and no-ops when _data/x/ is absent (the repository's committed state
# until backfill has run).
module XMirror
  YEAR_KEY = /\A\d{4}\z/

  # Resolves a post's parent and quoted references against everything the archive
  # knows, and decides how loudly to complain when one is missing.
  class Resolver
    def initialize(owner, data, years)
      @owner = owner
      @refs = data["refs"] || {}
      # A reference can point at an owned post rather than a ref: a thread spanning
      # two year files, or a self-quote. Neither is ever hydrated into refs.json.
      @owned = years.flat_map { |year| data[year] }
                    .each_with_object({}) { |post, index| index[post["id"]] = post }
      @pending = data.dig("state", "pending_ref_ids") || []
    end

    # Warns rather than raising. A missing parent is recoverable in both of its
    # forms: `forget` on a thread root legitimately leaves replies pointing at an
    # id that is gone, and an interrupted `hydrate` leaves a stranger's post
    # un-captured. Either way the thread still reads, headless — and a raise from
    # a generator would take every page of the site down, not just /x/. But it is
    # never silent, because the second form means the operator has work to do.
    def parent(post)
      id = post["in_reply_to_id"]
      return nil if id.nil?

      found = pair(id)
      warn_missing_parent(post, id) if found.nil?
      found
    end

    # Raises. A quote is part of what the post says; there is no partial rendering
    # of it that is still honest.
    def quote(post)
      id = post["quoted_id"]
      return nil if id.nil?

      pair(id) ||
        raise("x mirror: post #{post["id"]} quotes #{id}, which is in neither _data/x/refs.json " \
              "nor any year file. Restore that entry in refs.json, or drop the post with " \
              "`uv run x-mirror forget #{post["id"]}`. Re-running hydrate will not help: " \
              "the id is no longer in state.json's pending_ref_ids.")
    end

    private

    def pair(id)
      if (post = @owned[id])
        { "post" => post, "author" => @owner }
      elsif (ref = @refs[id])
        { "post" => ref, "author" => ref["author"] }
      end
    end

    def warn_missing_parent(post, id)
      message = "post #{post["id"]} replies to #{id}, which is in neither _data/x/refs.json nor any " \
                "year file — rendering the thread without its parent."
      if @pending.include?(id)
        message += " It is still listed in state.json's pending_ref_ids, so hydration did not finish: " \
                   "re-run `uv run x-mirror hydrate`."
      end
      Jekyll.logger.warn "x mirror:", message
    end
  end

  class Generator < Jekyll::Generator
    safe true

    TREES = ["curated", "full"].freeze

    def generate(site)
      data = site.data["x"] || {}
      years = data.keys.grep(YEAR_KEY).sort.reverse
      return if years.empty?

      owner = owner_author(site, data)
      resolver = Resolver.new(owner, data, years)
      mark_curated(data, years)

      markdown_by_year = {}

      years.each do |year|
        TREES.each do |tree|
          posts = tree == "curated" ? data[year].select { |p| p["curated"] } : data[year]
          groups = thread_groups(posts)
          parents, quotes = resolve_refs(groups, resolver)
          site.pages << year_page(site, tree, year, groups, parents, quotes, owner)
          if tree == "full"
            markdown_by_year[year] = year_markdown(site, year, groups, parents, quotes, owner)
            site.static_files << LlmExport::LlmFile.new(site, "llm/x", "#{year}.md", markdown_by_year[year])
          end
        end
      end

      TREES.each { |tree| site.pages << index_page(site, tree, years, data, owner) }
      site.pages << redirect_page(site)

      # Always emitted, even with nothing curated: the curated tree's copy pills
      # point here unconditionally, and a 404 breaks them.
      curated_posts = years.flat_map { |year| data[year].select { |p| p["curated"] } }
      groups = thread_groups(curated_posts)
      parents, quotes = resolve_refs(groups, resolver)
      markdown = curated_markdown(site, groups, parents, quotes, owner)
      site.static_files << LlmExport::LlmFile.new(site, "llm/x", "curated.md", markdown)
      site.static_files << LlmExport::LlmFile.new(site, "llm", "x.md", archive_markdown(site, markdown_by_year))
    end

    private

    # Runs the resolver once per post, shared by the HTML year page and the
    # Markdown emitter so a missing/dangling reference is only warned or raised
    # about a single time, not once per view.
    def resolve_refs(groups, resolver)
      parents = {}
      quotes = {}
      groups.each do |thread|
        # Only a group's first post can show a parent card: for every other post the
        # parent is the card immediately above it.
        root = thread.first
        parent = resolver.parent(root)
        parents[root["id"]] = parent if parent
        thread.each do |post|
          quoted = resolver.quote(post)
          quotes[post["id"]] = quoted if quoted
        end
      end
      [parents, quotes]
    end

    # The owner has no Ref — they are the site. Handle and name are configuration;
    # the avatar is pipeline output, so it comes from state.json and is simply
    # absent (blank circle) until backfill has run.
    def owner_author(site, data)
      handle = site.config["twitter_username"]
      display_name = site.config.dig("x", "display_name")
      raise "x mirror: _config.yml needs `twitter_username` and `x.display_name`" if handle.nil? || display_name.nil?

      { "handle" => handle, "display_name" => display_name,
        "avatar_path" => data.dig("state", "avatar_path") }
    end

    def year_page(site, tree, year, groups, parents, quotes, owner)
      page = Jekyll::PageWithoutAFile.new(site, site.source, "x/#{tree}/#{year}", "index.html")
      page.data.merge!(
        "layout" => "x_year",
        "title" => "X posts — #{year}#{tree == "curated" ? " (curated)" : ""}",
        "tree" => tree,
        "counterpart_url" => "/x/#{other_tree(tree)}/#{year}/",
        "year" => year,
        "owner" => owner,
        "thread_groups" => groups,
        "parents" => parents,
        "quotes" => quotes,
      )
      page
    end

    def index_page(site, tree, years, data, owner)
      page = Jekyll::PageWithoutAFile.new(site, site.source, "x/#{tree}", "index.html")
      counts = years.map do |year|
        posts = tree == "curated" ? data[year].count { |p| p["curated"] } : data[year].size
        { "year" => year, "count" => posts }
      end
      page.data.merge!(
        "layout" => "x_index",
        "title" => tree == "curated" ? "X posts — curated" : "X posts — full archive",
        "tree" => tree,
        "counterpart_url" => "/x/#{other_tree(tree)}/",
        "owner" => owner,
        "years" => counts,
      )
      page
    end

    def other_tree(tree)
      tree == "curated" ? "full" : "curated"
    end

    # /x/ itself just lands on the curated tree.
    def redirect_page(site)
      page = Jekyll::PageWithoutAFile.new(site, site.source, "x", "index.html")
      # The title puts it in minima's nav (see header_pages in _config.yml).
      page.data.merge!("layout" => nil, "permalink" => "/x/", "title" => "X Archive")
      # The script preserves the URL hash (#curate); the meta refresh is the
      # no-JS fallback and drops it.
      page.content = <<~HTML
        <!doctype html>
        <meta charset="utf-8">
        <script src="/assets/js/x-redirect.js"></script>
        <meta http-equiv="refresh" content="0; url=/x/curated/">
        <link rel="canonical" href="#{site.config["url"]}/x/curated/">
        <a href="/x/curated/">X posts (curated)</a>
      HTML
      page
    end

    # Hand-picked ids from _data/x/curated.json get post["curated"] = true; the curated
    # tree filters on it, and the full tree renders it as a star badge.
    def mark_curated(data, years)
      ids = data["curated"] || []
      by_id = years.flat_map { |year| data[year] }.to_h { |post| [post["id"], post] }
      missing = ids.reject { |id| by_id.key?(id) }
      raise "x mirror: curated.json lists unmirrored post(s) #{missing.join(", ")}" unless missing.empty?

      ids.each { |id| by_id[id]["curated"] = true }
    end

    def curated_markdown(site, groups, parents, quotes, owner)
      header = "# X posts — curated selection\n\n#{site.config["url"]}/x/curated/ — the full archive is at #{site.config["url"]}/llm/x.md"
      entries = entries_markdown(groups, parents, quotes, owner)
      entries = ["(nothing curated yet)"] if entries.empty?
      ([header] + entries).join("\n\n")
    end

    def entries_markdown(groups, parents, quotes, owner)
      groups.flat_map do |thread|
        root = thread.first
        thread.map { |post| post_markdown(post, owner, post.equal?(root) ? parents[root["id"]] : nil, quotes[post["id"]]) }
      end
    end

    # created_at is ISO 8601 UTC throughout, so string order is chronological. A thread
    # dashed off within one second ties on created_at, and sort_by is not stable — the
    # snowflake id breaks the tie, or the root can land mid-thread (and then render
    # twice: once as its successor's parent card, once as itself).
    def thread_groups(posts)
      posts.group_by { |post| post["thread_id"] }
           .values
           .map { |thread| thread.sort_by { |post| [post["created_at"], post["id"].to_i] } }
           .sort_by { |thread| thread.last["created_at"] }
           .reverse
    end

    # Same thread order as the HTML page (newest thread first, chronological within
    # a thread) so a reader can cross-reference the two views.
    def year_markdown(site, year, groups, parents, quotes, owner)
      header = "# X posts — #{year}\n\n#{site.config["url"]}/x/full/#{year}/"
      ([header] + entries_markdown(groups, parents, quotes, owner)).join("\n\n")
    end

    def archive_markdown(site, markdown_by_year)
      header = "# X posts — @#{site.config["twitter_username"]}"
      ([header] + markdown_by_year.values).join("\n\n")
    end

    # One post: a heading with its permalink, then the parent/quote context it
    # needs to be read on its own, then its own text and media. No HTML, no card
    # mimicry — this is what an LLM (or a human pasting into a chat) gets.
    def post_markdown(post, owner, parent, quoted)
      parts = ["### #{format_time(post["created_at"])} — https://x.com/#{owner["handle"]}/status/#{post["id"]}"]
      parts << context_block(parent, "") if parent
      parts << context_block(quoted, "Quoting ") if quoted
      parts << post_body(post)
      parts.join("\n\n")
    end

    def context_block(pair, prefix)
      post, author = pair["post"], pair["author"]
      return "> #{prefix}@#{author["handle"]}: [post no longer available]" if post["unavailable"]

      # A line break, not a space: collapsing to a space runs the text's last
      # word into the next line. Each continuation line still needs its own
      # "> " so the whole citation stays one blockquote.
      body = escape_structural(post["text"]).split("\n", -1).join("\n> ")
      lines = ["> #{prefix}@#{author["handle"]} (#{format_time(post["created_at"])}): #{body}"]
      (post["media"] || []).each { |item| lines << "> #{media_line(item)}" }
      lines.join("\n")
    end

    def post_body(post)
      media_lines = (post["media"] || []).map { |item| media_line(item) }
      ([escape_structural(post["text"])] + media_lines).join("\n\n")
    end

    def media_line(item)
      item["local_path"] ? "[photo: #{escape_structural(item["alt"])}]" : "[video: #{item["source_url"]}]"
    end

    def format_time(created_at)
      Time.parse(created_at).getutc.strftime("%Y-%m-%d %H:%M UTC")
    end

    # A line starting with a fence, heading, blockquote, list, ordered-list,
    # thematic-break, or setext-underline marker would be read by a Markdown
    # parser as document structure — an unclosed fence is the sharp edge,
    # since it swallows every following heading until the next fence (or
    # EOF), across post and year boundaries once /llm/x.md concatenates
    # everything. A single backslash on the trigger character defuses all of
    # it without touching anything else: this is plain text for a model or a
    # human pasting into a chat, not HTML, so unlike x_text_html nothing here
    # is escaped for its own sake — and unlike Round 1, a marker that
    # CommonMark itself requires a trailing space/tab/end-of-line for (list
    # bullets, headings, the ordered marker's delimiter) is only escaped when
    # that condition actually holds, so "3.5 hours later" and "-2 degrees"
    # come through untouched.
    def escape_structural(text)
      text.to_s.each_line.map { |line| escape_line(line) }.join
    end

    def escape_line(line)
      body = line.chomp
      indent = body[/\A[ \t]{0,3}/]
      rest = body[indent.length..]
      escaped = escape_fence(rest) || escape_blockquote(rest) || escape_heading(rest) ||
                escape_ordered(rest) || escape_bullet_or_rule(rest) || escape_html_block(rest)
      "#{indent}#{escaped || rest}#{line[body.length..]}"
    end

    # Backtick and tilde fences, and blockquotes, need no trailing space to
    # take effect, so these two ignore what follows the marker entirely.
    def escape_fence(rest)
      "\\#{rest}" if rest.start_with?("`", "~")
    end

    def escape_blockquote(rest)
      "\\#{rest}" if rest.start_with?(">")
    end

    def escape_heading(rest)
      run = rest[/\A#+/]
      return nil unless run && run.length <= 6 && [nil, " ", "\t"].include?(rest[run.length])

      "\\#{rest}"
    end

    # Only the '.'/')' delimiter needs escaping — the digits themselves are
    # never special, so leaving them bare keeps "1. real item" -> "1\. real item"
    # rather than "\1. real item".
    def escape_ordered(rest)
      digits = rest[/\A\d+/]
      return nil unless digits
      return nil unless %w[. )].include?(rest[digits.length])
      return nil unless [nil, " ", "\t"].include?(rest[digits.length + 1])

      "#{digits}\\#{rest[digits.length..]}"
    end

    BULLET_CHARS = %w[- + *].freeze
    # '-' and '=' need no minimum run: CommonMark accepts even one as a setext
    # underline. '_' and '*' only form a thematic break at three or more.
    THEMATIC_MIN_RUN = { "-" => 1, "=" => 1, "*" => 3, "_" => 3 }.freeze

    # '-', '+', '*' as a bullet marker (needs a trailing space/tab/EOL); '-',
    # '=', '*', '_' alone, spaces aside, for the rest of the line (a thematic
    # break or setext underline, which need no trailing space).
    def escape_bullet_or_rule(rest)
      return nil if rest.empty?

      marker = rest[0]
      bullet = BULLET_CHARS.include?(marker) && [nil, " ", "\t"].include?(rest[1])

      min = THEMATIC_MIN_RUN[marker]
      stripped = rest.delete(" \t")
      rule = min && stripped.length >= min && stripped.chars.uniq == [marker]

      "\\#{rest}" if bullet || rule
    end

    # CommonMark HTML blocks are the '<' analogue of an unclosed fence. Types 1
    # (<script>/<pre>/<style>/<textarea>) and 2–5 (comment, processing
    # instruction, declaration, CDATA) all ignore blank lines and run to their
    # own closing sequence or EOF, so an unclosed one swallows every later
    # '###' heading exactly as an unclosed fence does — through the whole
    # concatenated archive. Types 6 (a known block tag) and 7 (a line that's
    # nothing but one complete tag) are included too, per the brief, even
    # though both stop at the next blank line and so can't bridge across this
    # emitter's own blank-line-separated entries — they're the same escape, so
    # there's no reason to special-case them out. This does NOT HTML-escape
    # content: mid-line '<' (e.g. "2 < 3", "<script>alert(1)</script>" inside a
    # sentence) never matches, since CommonMark itself never starts an HTML
    # block mid-paragraph.
    HTML_BLOCK_TYPE1_TAGS = %w[script pre style textarea].freeze
    HTML_BLOCK_TYPE6_TAGS = %w[
      address article aside base basefont blockquote body caption center col
      colgroup dd details dialog dir div dl dt fieldset figcaption figure
      footer form frame frameset h1 h2 h3 h4 h5 h6 head header hr html
      iframe legend li link main menu menuitem nav noframes ol optgroup
      option p param section summary table tbody td tfoot th thead title tr
      track ul
    ].freeze
    HTML_TAG_NAME = /[A-Za-z][A-Za-z0-9-]*/
    HTML_ATTR = /\s+[A-Za-z_:][A-Za-z0-9_.:-]*(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?/
    HTML_OPEN_TAG = /<#{HTML_TAG_NAME}(?:#{HTML_ATTR})*\s*\/?>/
    HTML_CLOSE_TAG = %r{</#{HTML_TAG_NAME}\s*>}
    TYPE1_RE = /\A<(#{HTML_BLOCK_TYPE1_TAGS.join("|")})(?=[\s>]|\z)/i
    # Types 2 (comment), 3 (processing instruction), 5 (CDATA) and 4
    # (declaration: '<!' plus an ASCII letter, e.g. '<!DOCTYPE html') — each is
    # a fixed prefix, with no tag grammar involved.
    TYPE2345_RE = /\A(?:<!--|<\?|<!\[CDATA\[|<![A-Za-z])/
    TYPE6_RE = /\A<\/?(#{HTML_BLOCK_TYPE6_TAGS.join("|")})(?=[\s\/>]|\z)/i
    TYPE7_RE = /\A(?:#{HTML_OPEN_TAG}|#{HTML_CLOSE_TAG})[ \t]*\z/
    HTML_BLOCK_RES = [TYPE1_RE, TYPE2345_RE, TYPE6_RE, TYPE7_RE].freeze

    def escape_html_block(rest)
      return nil unless rest.start_with?("<")

      "\\#{rest}" if HTML_BLOCK_RES.any? { |re| rest =~ re }
    end
  end
end
