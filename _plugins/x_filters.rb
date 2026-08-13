require "cgi"

module XFilters
  URL = %r{https?://[^\s<]+}
  MENTION = /(^|\s)@(\w{1,15})/

  # Post text is stored raw; escape first, then linkify, so no stored text can
  # inject markup.
  def x_text_html(text)
    escaped = CGI.escapeHTML(text.to_s)
    linked = escaped.gsub(URL) { |url| %(<a href="#{url}" rel="nofollow noopener">#{url}</a>) }
    mentioned = linked.gsub(MENTION) do
      %(#{Regexp.last_match(1)}<a href="https://x.com/#{Regexp.last_match(2)}">@#{Regexp.last_match(2)}</a>)
    end
    mentioned.gsub("\n", "<br>")
  end
end

Liquid::Template.register_filter(XFilters)
