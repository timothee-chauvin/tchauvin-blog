# Shared by llm_generator.rb (posts) and x_generator.rb (X mirror): a Jekyll
# static file whose contents are generated in memory rather than read from disk.
module LlmExport
  class LlmFile < Jekyll::StaticFile
    def initialize(site, dir, name, content)
      super(site, site.source, dir, name)
      @content = content
    end

    def write(dest)
      dest_path = destination(dest)
      FileUtils.mkdir_p(File.dirname(dest_path))
      File.write(dest_path, @content)
      true
    end

    # No backing source file, so skip the mtime stat Jekyll would otherwise do.
    def modified?
      true
    end
  end
end
