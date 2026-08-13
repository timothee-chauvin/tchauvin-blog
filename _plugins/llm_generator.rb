# Emits an LLM-friendly Markdown copy of each post at /llm/<slug>.md.
# Runs at build time in full (non-safe) Jekyll, so post.content here is the raw
# Markdown source, before rendering. This keeps _posts/ the single source of
# truth: nothing is committed or hand-synced.
module LlmExport
  class Generator < Jekyll::Generator
    safe true

    def generate(site)
      base_url = site.config["url"].to_s
      site.posts.docs.each do |post|
        title  = post.data["title"].to_s
        url    = "#{base_url}#{post.url}"
        author = post.data["cite_author"] || site.config.fetch("cite_author")
        date   = post.date.strftime("%b %-d, %Y")

        header = ["# #{title}", "By #{author} · #{date}", url].join("\n\n")
        text   = "#{header}\n\n#{post.content}"
        # Link rather than duplicate the citation feature (_includes/cite_boxes.html);
        # an LLM can fetch the anchor on the rare occasion it needs to cite.
        text += "\n\n## How to cite\n\nSee #{url}#cite" if post.data["cite"]

        path = "llm#{post.url}.md" # post.url is "/<slug>"
        site.static_files << LlmFile.new(site, File.dirname(path), File.basename(path), text)
      end
    end
  end
end
