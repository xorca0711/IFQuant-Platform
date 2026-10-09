/**
 * Native RGB intake bridge for a current QuPath image (including VSI/ETS).
 * Run with one JSON config argument and NO --save. Creates a fresh directory.
 * QuPath 0.7 API: OMEPyramidWriter.Builder and QP.exportObjectsToGeoJson.
 * No stain conversion, classifier, grading, or project mutation is performed.
 */
import qupath.lib.io.GsonTools
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.security.MessageDigest
import qupath.lib.images.writers.ome.OMEPyramidWriter
import qupath.lib.common.GeneralTools

def check = { boolean ok, String reason -> if (!ok) throw new IllegalArgumentException(reason) }
def hash = { Path path ->
    def md = MessageDigest.getInstance('SHA-256')
    Files.newInputStream(path).withCloseable { stream ->
        byte[] buffer = new byte[1024 * 1024]
        int n
        while ((n = stream.read(buffer)) > 0) md.update(buffer, 0, n)
    }
    md.digest().encodeHex().toString()
}
def emit = { Path path, value ->
    Files.writeString(path, GsonTools.getInstance(true).toJson(value), StandardOpenOption.CREATE_NEW)
}
check(args.size() == 1, 'Supply one brightfield config path')
def configPath = Path.of(args[0]).toAbsolutePath().normalize()
def cfg = GsonTools.getInstance().fromJson(Files.readString(configPath), Map.class)
check(cfg.keySet() == (['schema_version', 'output_directory', 'expected_server_name', 'source_members',
                       'subject', 'pixel_size_x_um', 'pixel_size_y_um', 'z', 't', 'script_path',
                       'expected_script_sha256'] as Set), 'Unknown/missing config fields')
check(cfg.schema_version == 'ifquant.qupath-brightfield/1', 'Unsupported bridge config')
check(hash(Path.of(cfg.script_path)) == cfg.expected_script_sha256, 'Bridge script hash mismatch')
def server = getCurrentServer()
check(server != null && server.isRGB() && server.getPixelType().toString() == 'UINT8', 'Native UINT8 RGB server required')
check(server.getMetadata().getName() == cfg.expected_server_name, 'Unexpected image server')
check(cfg.z instanceof Number && cfg.z == cfg.z.intValue() && cfg.z >= 0 && cfg.z < server.nZSlices(), 'Explicit valid z required')
check(cfg.t instanceof Number && cfg.t == cfg.t.intValue() && cfg.t >= 0 && cfg.t < server.nTimepoints(), 'Explicit valid t required')
check(cfg.pixel_size_x_um instanceof Number && Double.isFinite(cfg.pixel_size_x_um.doubleValue()) && cfg.pixel_size_x_um > 0 &&
      cfg.pixel_size_y_um instanceof Number && Double.isFinite(cfg.pixel_size_y_um.doubleValue()) && cfg.pixel_size_y_um > 0,
      'Positive finite calibration required')
check(cfg.subject.keySet() == (['subject_id', 'species', 'specimen_id', 'section_id'] as Set) &&
      cfg.subject.values().every { it instanceof String && !it.trim().isEmpty() }, 'Subject identity required')
check(cfg.source_members instanceof List && !cfg.source_members.isEmpty(), 'List every raw source member')
def members = cfg.source_members.collect { Path.of(it).toRealPath() }
check(members.toSet().size() == members.size(), 'Duplicate source member')
server.getURIs().each { uri ->
    check(uri.scheme == 'file' && members.contains(Path.of(uri).toRealPath()), 'Server URI absent from source inventory')
}
def inventory = members.collect { [path: it.toString(), sha256: hash(it), size_bytes: Files.size(it)] }
def calibration = server.getPixelCalibration()
if (calibration.hasPixelSizeMicrons()) {
    check(Math.abs(calibration.getPixelWidthMicrons() - cfg.pixel_size_x_um) < 1e-6 &&
          Math.abs(calibration.getPixelHeightMicrons() - cfg.pixel_size_y_um) < 1e-6,
          'Declared calibration differs from server; resolve before exporting')
}
def root = Path.of(cfg.output_directory).toAbsolutePath().normalize()
Files.createDirectories(root.parent)
Files.createDirectory(root)
try {
    def image = root.resolve('brightfield.ome.tif')
    new OMEPyramidWriter.Builder(server).tileSize(512).channelsInterleaved().bigTiff()
        .uncompressed().scaledDownsampling(1.0, 2.0).zSlice(cfg.z.intValue()).timePoint(cfg.t.intValue())
        .parallelize(1).build().writeSeries(image.toString())
    exportObjectsToGeoJson(getAnnotationObjects().findAll { it.getROI().getZ() == cfg.z && it.getROI().getT() == cfg.t },
                          root.resolve('annotations.geojson').toString(), 'FEATURE_COLLECTION')
    inventory.each { check(hash(Path.of(it.path)) == it.sha256, 'Raw source changed during export') }
    def bridge = [schema_version: 'ifquant.qupath-derivative/1', qupath_version: GeneralTools.getVersion(),
                  config_sha256: hash(configPath), script_sha256: cfg.expected_script_sha256,
                  source_members: inventory, z: cfg.z, t: cfg.t, original_server_name: cfg.expected_server_name,
                  transform: 'identity_xy_native_pixels_selected_plane', compression: 'uncompressed',
                  scientific_validation: false]
    emit(root.resolve('derivation.json'), bridge)
    def allFiles = [image, root.resolve('derivation.json')] + members
    emit(root.resolve('source.json'), [schema_version: 'ifquant.image-source/1', subject: cfg.subject,
        modality: 'he', calibration_source: 'user_declared_base_pixel_size',
        files: allFiles.collect { [path: it.toString(), sha256: hash(it), size_bytes: Files.size(it)] },
        selection: [reader: 'tiff', series: 0, level: 0],
        grid: [width: server.getWidth(), height: server.getHeight(), base_width: server.getWidth(),
               base_height: server.getHeight(), channels: 3, dtype: 'uint8', scale_x: 1, scale_y: 1,
               pixel_size_x_um: cfg.pixel_size_x_um, pixel_size_y_um: cfg.pixel_size_y_um]])
    println('IFQUANT_BRIGHTFIELD_EXPORTED ' + root)
} catch (Exception ex) {
    emit(root.resolve('failure.json'), [status: 'failed', error: ex.toString()])
    throw ex
}
