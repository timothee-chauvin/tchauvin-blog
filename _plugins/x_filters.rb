require "cgi"

module XFilters
  # Mirrors twitter-text's URL extraction: parentheses must balance, and a URL
  # never ends in sentence punctuation. Without this, "see https://a.b/c)." links
  # to "/c)." — a 404 the site itself then advertises to crawlers.
  URL_CHAR = %r{[^\s()<]}
  URL_END_CHAR = %r{[^\s()<.,:;!?'"]}
  PAREN_GROUP = %r{\([^\s()<]*\)}
  URL = %r{https?://(?:#{PAREN_GROUP}|#{URL_CHAR})*(?:#{PAREN_GROUP}|#{URL_END_CHAR})}
  MENTION = /(^|\s)@(\w{1,15})/

  # Post text is stored raw; every segment is escaped before any markup is
  # added, so no stored text can inject markup. URLs are matched on the raw text
  # (escaping first would glue entities like &#39; onto them).
  def x_text_html(text)
    text.to_s.split(/(#{URL})/).each_slice(2).map do |plain, url|
      html = CGI.escapeHTML(plain).gsub(MENTION) do
        %(#{Regexp.last_match(1)}<a href="https://x.com/#{Regexp.last_match(2)}">@#{Regexp.last_match(2)}</a>)
      end
      html << %(<a href="#{CGI.escapeHTML(url)}" rel="nofollow noopener">#{CGI.escapeHTML(url)}</a>) if url
      html
    end.join.gsub("\n", "<br>")
  end
end

Liquid::Template.register_filter(XFilters)
