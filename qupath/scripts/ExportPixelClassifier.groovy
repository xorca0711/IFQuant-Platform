/** Export a bounded, native-resolution classifier comparison region without saving a project. */
import qupath.lib.io.GsonTools
import qupath.lib.regions.RegionRequest
import qupath.opencv.ml.pixel.PixelClassifiers
import qupath.opencv.ml.pixel.PixelClassifierTools
import qupath.lib.common.GeneralTools
import java.nio.file.Path
import java.nio.file.Files
import java.nio.file.StandardOpenOption
import java.security.MessageDigest
import javax.imageio.ImageIO
import java.awt.image.BufferedImage

def check = { boolean ok, String why -> if (!ok) throw new IllegalArgumentException(why) }
def hash = { Path path ->
    def digest = MessageDigest.getInstance('SHA-256')
    Files.newInputStream(path).withCloseable { stream ->
        byte[] buffer = new byte[1024 * 1024]
        int n
        while ((n = stream.read(buffer)) > 0) digest.update(buffer, 0, n)
    }
    digest.digest().encodeHex().toString()
}
check(args.size() == 1, 'One config path required')
def configPath = Path.of(args[0]).toAbsolutePath()
def cfg = GsonTools.getInstance().fromJson(Files.readString(configPath), Map.class)
check(cfg.keySet() == (['schema_version', 'classifier', 'classifier_sha256', 'source_members',
    'window_xywh', 'output_directory', 'pixel_size_x_um', 'pixel_size_y_um', 'subject',
    'model_training_reference'] as Set), 'Unexpected/missing classifier export config fields')
check(cfg.schema_version == 'ifquant.qupath-pixel-region/1', 'Unsupported classifier region config')
check(cfg.model_training_reference instanceof String && !cfg.model_training_reference.trim().isEmpty(), 'Training provenance required')
def server = getCurrentServer()
check(server != null && server.isRGB() && server.nZSlices() == 1 && server.nTimepoints() == 1, '2D RGB source required')
check(cfg.source_members instanceof List && !cfg.source_members.isEmpty(), 'Source inventory required')
def members = cfg.source_members.collect { Path.of(it).toRealPath() }
check(members.toSet().size() == members.size(), 'Duplicate source member')
server.getURIs().each { uri -> check(uri.scheme == 'file' && members.contains(Path.of(uri).toRealPath()), 'Unbound source URI') }
def inventory = members.collect { [path: it.toString(), sha256: hash(it), size_bytes: Files.size(it)] }
check(cfg.subject.keySet() == (['subject_id', 'species', 'specimen_id', 'section_id'] as Set) &&
      cfg.subject.values().every { it instanceof String && !it.trim().isEmpty() }, 'Subject identity required')
check([cfg.pixel_size_x_um, cfg.pixel_size_y_um].every { it instanceof Number && Double.isFinite(it.doubleValue()) && it > 0 }, 'Calibration required')
def cal = server.getPixelCalibration()
if (cal.hasPixelSizeMicrons())
    check(Math.abs(cal.getPixelWidthMicrons()-cfg.pixel_size_x_um) < 1e-6 && Math.abs(cal.getPixelHeightMicrons()-cfg.pixel_size_y_um) < 1e-6, 'Calibration conflict')
check(cfg.window_xywh instanceof List && cfg.window_xywh.size() == 4 &&
      cfg.window_xywh.every { it instanceof Number && it == it.intValue() }, 'Integer XYWH required')
def (x, y, w, h) = cfg.window_xywh.collect { it.intValue() }
check(x >= 0 && y >= 0 && w > 0 && h > 0 && x+w <= server.getWidth() && y+h <= server.getHeight() &&
      (long) w*h <= 16000000, 'Region exceeds source/capacity')
def model = Path.of(cfg.classifier).toRealPath()
check(hash(model) == cfg.classifier_sha256, 'Classifier bytes differ')
def classifier = PixelClassifiers.readClassifier(model)
def classified = PixelClassifierTools.createPixelClassificationServer(getCurrentImageData(), classifier)
try {
    check(classified.getMetadata().getChannelType().name() == 'CLASSIFICATION', 'Discrete label classifier required; probabilities cannot be treated as labels')
    def request = RegionRequest.createInstance(classified.getPath(), 1.0, x, y, w, h)
    def labels = classified.readRegion(request)
    check(labels.getWidth() == w && labels.getHeight() == h && labels.getRaster().getNumBands() == 1, 'Unexpected output label grid')
    def original = server.readRegion(RegionRequest.createInstance(server.getPath(), 1.0, x, y, w, h))
    def root = Path.of(cfg.output_directory).toAbsolutePath()
    Files.createDirectories(root.parent)
    Files.createDirectory(root)
    def codes = classified.getMetadata().getClassificationLabels().keySet()
    check(!codes.isEmpty() && codes.every { it >= 0 && it <= 65535 }, 'Unsupported label values')
    def numeric = new BufferedImage(w, h, codes.max() <= 255 ? BufferedImage.TYPE_BYTE_GRAY : BufferedImage.TYPE_USHORT_GRAY)
    numeric.getRaster().setRect(labels.getRaster())
    check(ImageIO.write(numeric, 'png', root.resolve('prediction.png').toFile()), 'PNG label writer unavailable')
    check(ImageIO.write(original, 'png', root.resolve('source.png').toFile()), 'PNG source writer unavailable')
    inventory.each { check(hash(Path.of(it.path)) == it.sha256, 'Source changed during classification') }
    check(hash(model) == cfg.classifier_sha256, 'Classifier changed during execution')
    def report = [schema_version: 'ifquant.qupath-pixel-region-result/1', config: cfg, config_sha256: hash(configPath),
        qupath_version: GeneralTools.getVersion(), source_members: inventory,
        output_labels: classified.getMetadata().getClassificationLabels().collectEntries { k,v -> [(k.toString()):v.toString()] },
        scientific_validation: false, scope: 'bounded label execution; accuracy requires independent reviewed reference masks']
    Files.writeString(root.resolve('derivation.json'), GsonTools.getInstance(true).toJson(report), StandardOpenOption.CREATE_NEW)
    def files = [root.resolve('source.png'), root.resolve('derivation.json'), model] + members
    def source = [schema_version: 'ifquant.image-source/1', subject: cfg.subject, modality: 'he',
        calibration_source: 'user_declared_base_pixel_size', selection: [reader: 'pillow', series: 0, level: 0],
        files: files.collect { [path: it.toString(), sha256: hash(it), size_bytes: Files.size(it)] },
        grid: [width: w, height: h, base_width: w, base_height: h, channels: 3, dtype: 'uint8', scale_x: 1, scale_y: 1,
               pixel_size_x_um: cfg.pixel_size_x_um, pixel_size_y_um: cfg.pixel_size_y_um]]
    Files.writeString(root.resolve('source.json'), GsonTools.getInstance(true).toJson(source), StandardOpenOption.CREATE_NEW)
    println('IFQUANT_PIXEL_REGION_EXPORTED ' + root)
} finally {
    classified.close()
}
