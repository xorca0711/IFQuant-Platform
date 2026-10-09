/** Synthetic threshold fixture only; never a trained histopathology model. */
import qupath.opencv.ml.pixel.PixelClassifiers
import qupath.lib.objects.classes.PathClass
import qupath.lib.images.servers.PixelCalibration
import java.nio.file.Path
import java.nio.file.Files
if (args.size() != 1 || Files.exists(Path.of(args[0])))
    throw new IllegalArgumentException('Supply one new classifier output path')
def model = PixelClassifiers.createThresholdClassifier(PixelCalibration.getDefaultInstance(), 0, 128.0,
    PathClass.fromString('fixture-below'), PathClass.fromString('fixture-above'))
PixelClassifiers.writeClassifier(model, Path.of(args[0]))
