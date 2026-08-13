source "https://rubygems.org"
# Hello! This is where you manage which Jekyll version is used to run.
# When you want to use a different version, change it below, save the
# file and run `bundle install`. Run Jekyll with `bundle exec`, like so:
#
#     bundle exec jekyll serve
#
# This will help ensure the proper Jekyll version is running.
# Happy Jekylling!
# We deploy via a GitHub Actions workflow (.github/workflows/pages.yml) that runs
# `jekyll build` in full mode, so we use the standalone jekyll gem rather than the
# `github-pages` meta-gem. That meta-gem forces safe mode, which disables _plugins/
# (we need _plugins/llm_generator.rb). Jekyll is pinned to the 3.9 line GitHub Pages
# was building us on, so rendered output is unchanged.
gem "jekyll", "~> 3.9"
# This is the default theme for new Jekyll sites. You may change this to anything you like.
gem "minima", "~> 2.5"
# If you have any plugins, put them here!
group :jekyll_plugins do
  gem "jekyll-feed", "~> 0.12"
end

# GFM is Jekyll's default kramdown input; previously provided transitively by the
# github-pages gem. Declared explicitly so markdown rendering is unchanged.
gem "kramdown-parser-gfm"

# Windows and JRuby does not include zoneinfo files, so bundle the tzinfo-data gem
# and associated library.
platforms :mingw, :x64_mingw, :mswin, :jruby do
  gem "tzinfo", ">= 1", "< 3"
  gem "tzinfo-data"
end

# Performance-booster for watching directories on Windows
gem "wdm", "~> 0.1.1", :platforms => [:mingw, :x64_mingw, :mswin]

# Lock `http_parser.rb` gem to `v0.6.x` on JRuby builds since newer versions of the gem
# do not have a Java counterpart.
gem "http_parser.rb", "~> 0.6.0", :platforms => [:jruby]

# https://github.com/jekyll/jekyll/issues/8523
gem "webrick", "~> 1.8.1"

# Only for scripts/check-llm-x, which parses the generated /llm/x.md with a real
# CommonMark implementation. Jekyll never requires this group (it only auto-requires
# :jekyll_plugins), so the site build and the deploy are unaffected.
group :checks do
  gem "commonmarker", "~> 2.9"
end
