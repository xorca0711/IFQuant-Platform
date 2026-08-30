/*
 * IFQuant Platform deterministic QuPath cell-object exporter.
 *
 * Engineering pilot only: no scientific validation, backend equivalence,
 * model universality, or endpoint authorization is implied.
 *
 * Runtime boundary: QuPath >= 0.6.0 and < 0.8.0.
 * IFQUANT_SCRIPT_SENTINEL:ifquant.qupath-cell-exporter/v1@1.0.0
 */

import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import org.locationtech.jts.geom.Geometry
import org.locationtech.jts.geom.PrecisionModel
import org.locationtech.jts.geom.util.AffineTransformation
import org.locationtech.jts.io.WKTWriter
import org.locationtech.jts.precision.GeometryPrecisionReducer
import qupath.lib.objects.PathCellObject
import qupath.lib.scripting.QP
import qupath.lib.scripting.ScriptAttributes

import java.math.BigDecimal
import java.math.BigInteger
import java.net.URI
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.security.DigestOutputStream
import java.security.MessageDigest
import java.time.Instant
import java.util.regex.Pattern

final class IfQuantV1Exporter {

    static final String CONFIG_SCHEMA =
        "ifquant.qupath-pilot-config/1.0.0"
    static final String SCRIPT_CONTRACT =
        "ifquant.qupath-cell-exporter/v1"
    static final String SCRIPT_VERSION = "1.0.0"
    static final String SCRIPT_FILENAME = "DetectCellsAndExport.groovy"
    static final String SCRIPT_SENTINEL =
        "IFQUANT_SCRIPT_SENTINEL:ifquant.qupath-cell-exporter/v1@1.0.0"
    static final String PILOT_STATUS =
        "unvalidated_engineering_pilot"
    static final String CONTRACT_VERSION = "1.0.0"
    static final String IMAGE_SCHEMA =
        "https://ifquant.org/contracts/platform/v1/image-manifest.schema.json"
    static final String CHANNEL_SCHEMA =
        "https://ifquant.org/contracts/platform/v1/channel-map.schema.json"
    static final String ANNOTATION_SCHEMA =
        "https://ifquant.org/contracts/platform/v1/annotation-set.schema.json"
    static final String SEGMENTATION_SCHEMA =
        "https://ifquant.org/contracts/platform/v1/segmentation-run.schema.json"
    static final String CELL_SCHEMA =
        "https://ifquant.org/contracts/platform/v1/cell-object.schema.json"
    static final String PACKAGE_SCHEMA =
        "https://ifquant.org/contracts/platform/v1/cell-object-package.schema.json"
    static final String DEFINITION_SCHEMA =
        "https://ifquant.org/contracts/platform/v1/measurement-definition.schema.json"
    static final String PARAMETER_SCHEMA =
        "https://ifquant.org/contracts/platform/v1/parameter-set.schema.json"
    static final String METHOD_INSTANCE_DOMAIN =
        "ifquant-platform-method-instance/v1"
    static final String WATERSHED_PLUGIN =
        "qupath.imagej.detect.cells.WatershedCellDetection"
    static final String IMAGE_MANIFEST_PATH =
        "manifests/image-manifest.json"
    static final String CHANNEL_MANIFEST_PATH =
        "manifests/channel-map.json"
    static final String ANNOTATION_MANIFEST_PATH =
        "manifests/annotation-set.json"
    static final String SEGMENTATION_MANIFEST_PATH =
        "manifests/segmentation-run.json"
    static final String CELL_OBJECTS_PATH = "cell_objects.jsonl"
    static final String PACKAGE_PATH = "package.json"
    static final String CANDIDATE_DISPOSITIONS_PATH =
        "qc/candidate-dispositions.jsonl"
    static final String CANDIDATE_DISPOSITIONS_MANIFEST_PATH =
        "qc/candidate-dispositions-manifest.json"
    static final String CANDIDATE_DISPOSITION_SCHEMA =
        "ifquant.qc-candidate-disposition/1.0.0"
    static final String CANDIDATE_DISPOSITIONS_MANIFEST_SCHEMA =
        "ifquant.qc-candidate-dispositions-manifest/1.0.0"

    static final int WKT_DIMENSIONS = 2
    static final int WKT_PRECISION_DECIMALS = 6
    static final double WKT_PRECISION_SCALE =
        Math.pow(10.0d, WKT_PRECISION_DECIMALS)
    static final BigInteger MAX_SAFE_INTEGER =
        new BigInteger("9007199254740991")
    static final Pattern JSON_NUMBER = Pattern.compile(
        "-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
    )
    static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}")
    static final Pattern IDENTIFIER = Pattern.compile(
        "[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}"
    )
    static final Pattern SEMVER = Pattern.compile(
        "[0-9]+\\.[0-9]+\\.[0-9]+"
    )
    static final Pattern CODE_REVISION = Pattern.compile("[0-9a-f]{7,64}")

    static void fail(String message) {
        throw new IllegalStateException(
            "IFQUANT_PILOT_ERROR: " + message
        )
    }

    static void run(String[] argv, Object executingScriptPathValue) {
        QP.checkVersionRange("0.6.0", "0.8.0")
        verifyCanonicalVectors()
        if (argv == null || argv.length != 1) {
            fail(
                "expected exactly one configuration path in args[0]; received " +
                (argv == null ? 0 : argv.length)
            )
        }

        Path configPath = Paths.get(argv[0]).toAbsolutePath().normalize()
        if (!Files.isRegularFile(configPath) || !Files.isReadable(configPath)) {
            fail("configuration is not a readable regular file: " + configPath)
        }
        byte[] configBytes = Files.readAllBytes(configPath)
        Map<String, Object> config = requireMap(
            parseStrictJson(configBytes),
            "configuration"
        )
        validateConfig(config)
        String configFileSha256 = sha256(configBytes)
        String configCanonicalSha256 = canonicalSha256(config)

        Map<String, Object> executionConfig = requireMap(
            config.get("execution"),
            "execution"
        )
        Path configuredScriptPath = resolveInputPath(
            configPath,
            requireResolvedString(
                executionConfig.get("script_path"),
                "execution.script_path"
            )
        )
        if (!Files.isRegularFile(configuredScriptPath) ||
            !Files.isReadable(configuredScriptPath)) {
            fail(
                "configured script_path is not a readable file: " +
                configuredScriptPath
            )
        }
        Path scriptPath = requireExecutingScriptPath(executingScriptPathValue)
        if (scriptPath != configuredScriptPath) {
            fail(
                "QuPath ScriptAttributes.FILE_PATH does not equal normalized " +
                "execution.script_path; executing=" + scriptPath +
                ", configured=" + configuredScriptPath
            )
        }
        if (!Files.isRegularFile(scriptPath) || !Files.isReadable(scriptPath)) {
            fail("executing script is not a readable regular file: " + scriptPath)
        }
        if (scriptPath.getFileName().toString() != SCRIPT_FILENAME) {
            fail("execution.script_path filename must equal " + quoted(SCRIPT_FILENAME))
        }
        String scriptText = decodeStrictUtf8(
            Files.readAllBytes(scriptPath),
            "configured script"
        )
        if (countOccurrences(scriptText, SCRIPT_SENTINEL) != 2) {
            fail("configured script must contain exactly the executable and header sentinel")
        }
        String scriptSha256 = sha256File(scriptPath)
        String expectedScriptSha256 = requireSha256(
            executionConfig.get("expected_script_sha256"),
            "execution.expected_script_sha256"
        )
        if (scriptSha256 != expectedScriptSha256) {
            fail(
                "script hash mismatch: expected " + expectedScriptSha256 +
                " but found " + scriptSha256
            )
        }

        Map<String, Object> methodBinding = loadMeasurementMethod(
            configPath,
            requireMap(
                config.get("measurement_method"),
                "measurement_method"
            ),
            requireMap(
                config.get("measurement_mappings"),
                "measurement_mappings"
            ),
            typedMapList(
                requireList(
                    requireMap(
                        config.get("channel_map"),
                        "channel_map"
                    ).get("channels"),
                    "channel_map.channels"
                ),
                "channel_map.channels"
            )
        )

        if (QP.getProject() == null) {
            fail(
                "no current QuPath project; this pilot is project-only and " +
                "requires --project plus --image with saved FLUORESCENCE " +
                "image data and existing annotations"
            )
        }
        if (QP.getProjectEntry() == null) {
            fail(
                "the current image is not a QuPath project entry; select a " +
                "saved project image with --project plus --image"
            )
        }

        Path outputDirectory = resolveInputPath(
            configPath,
            requireResolvedString(
                config.get("output_directory"),
                "output_directory"
            )
        )
        prepareEmptyOutputDirectory(outputDirectory)

        def imageData = QP.getCurrentImageData()
        if (imageData == null) {
            fail(
                "no current project image; invoke with QuPath script " +
                "--project plus --image"
            )
        }
        if (!imageData.isFluorescence()) {
            fail(
                "this DAPI Watershed pilot requires QuPath image type " +
                "FLUORESCENCE; brightfield, unset, and other types are rejected"
            )
        }
        String runtimeVersion = requireQuPathVersion()

        Map<String, Object> imageConfig = requireMap(
            config.get("image"),
            "image"
        )
        Map<String, Object> imageRuntime = verifyCurrentImage(
            imageData,
            imageConfig,
            typedMapList(
                requireList(
                    requireMap(
                        config.get("channel_map"),
                        "channel_map"
                    ).get("channels"),
                    "channel_map.channels"
                ),
                "channel_map.channels"
            )
        )
        Map<String, Object> pixelCalibration =
            (Map<String, Object>) imageRuntime.get("pixel_calibration")
        Map<String, Object> coordinateSpace =
            (Map<String, Object>) imageRuntime.get("coordinate_space")

        Map<String, Object> packageConfig = requireMap(
            config.get("package"),
            "package"
        )
        String packageId = packageConfig.get("package_id").toString()
        String imageId = imageConfig.get("image_id").toString()
        String biologicalUnitId =
            imageConfig.get("biological_unit_id").toString()
        Map<String, Object> channelConfig = requireMap(
            config.get("channel_map"),
            "channel_map"
        )
        String channelMapId =
            channelConfig.get("channel_map_id").toString()
        Map<String, Object> annotationConfig = requireMap(
            config.get("annotation_set"),
            "annotation_set"
        )
        String annotationSetId =
            annotationConfig.get("annotation_set_id").toString()
        Map<String, Object> segmentationConfig = requireMap(
            config.get("segmentation"),
            "segmentation"
        )
        String segmentationRunId =
            segmentationConfig.get("segmentation_run_id").toString()
        Map<String, Object> provenanceConfig = requireMap(
            config.get("provenance"),
            "provenance"
        )

        def hierarchy = imageData.getHierarchy()
        String classification = annotationConfig
            .get("classification")
            .toString()
        List selectedAnnotations = hierarchy.getAnnotationObjects()
            .findAll {
                it.getPathClass() != null &&
                it.getPathClass().toString() == classification
            }
            .toList()
        if (selectedAnnotations.isEmpty()) {
            fail(
                "no existing annotations match classification " +
                quoted(classification)
            )
        }

        Map<Object, Map<String, Object>> annotationByObject =
            buildAnnotationRecords(
                selectedAnnotations,
                imageId,
                annotationSetId,
                classification
            )
        String annotationContentSha256 = annotationContentSha256(
            annotationConfig,
            imageId,
            coordinateSpace.get("coordinate_space_id").toString(),
            annotationByObject.values().toList()
        )
        String expectedAnnotationContentSha256 = requireSha256(
            annotationConfig.get("expected_content_sha256"),
            "annotation_set.expected_content_sha256"
        )
        if (annotationContentSha256 != expectedAnnotationContentSha256) {
            fail(
                "selected annotation content hash mismatch: expected " +
                expectedAnnotationContentSha256 + " but found " +
                annotationContentSha256
            )
        }
        Set<Object> selectedSet = Collections.newSetFromMap(
            new IdentityHashMap<Object, Boolean>()
        )
        selectedSet.addAll(selectedAnnotations)
        List allPreexistingDetections = hierarchy.getDetectionObjects().toList()
        Set<Object> preRunDetectionSet = Collections.newSetFromMap(
            new IdentityHashMap<Object, Boolean>()
        )
        preRunDetectionSet.addAll(allPreexistingDetections)
        List preexistingDetections = allPreexistingDetections
            .findAll {
                hasSelectedAnnotationAncestor(it, selectedSet) ||
                intersectsAnyAnnotation(it, selectedAnnotations)
            }
            .toList()
        if (!preexistingDetections.isEmpty()) {
            fail(
                "selected annotations already contain " +
                preexistingDetections.size() +
                " detection object(s); refusing destructive or ambiguous rerun"
            )
        }
        hierarchy.getSelectionModel().setSelectedObjects(
            selectedAnnotations,
            selectedAnnotations.get(0)
        )

        String backend = requireMap(
            segmentationConfig.get("backend"),
            "segmentation.backend"
        ).get("kind").toString()
        if (backend == "stardist" || backend == "instanseg") {
            fail(
                "CANDIDATE_BACKEND_NOT_IMPLEMENTED: " + backend +
                " is registered behind the v1 interface but this script " +
                "implements native_qupath only"
            )
        }
        if (backend != "native_qupath") {
            fail("unsupported segmentation backend: " + backend)
        }
        String configuredVersion = requireMap(
            segmentationConfig.get("backend"),
            "segmentation.backend"
        ).get("version").toString()
        if (runtimeVersion != configuredVersion) {
            fail(
                "configured QuPath version " + configuredVersion +
                " does not equal runtime " + runtimeVersion
            )
        }

        String pluginClass =
            segmentationConfig.get("plugin_class").toString()
        Map<String, Object> pluginParameters = requireMap(
            segmentationConfig.get("parameters"),
            "segmentation.parameters"
        )
        Instant pluginStartedAt = Instant.now()
        boolean completed = QP.runPlugin(
            pluginClass,
            imageData,
            pluginParameters
        )
        Instant pluginCompletedAt = Instant.now()
        if (!completed) {
            fail("WatershedCellDetection returned false")
        }

        List newDetections = hierarchy.getDetectionObjects()
            .findAll { !preRunDetectionSet.contains(it) }
            .toList()
        List nonCellDetections = newDetections
            .findAll { !(it instanceof PathCellObject) }
        if (!nonCellDetections.isEmpty()) {
            fail("native cell detector produced non-cell detection objects")
        }
        String boundaryPolicy = segmentationConfig.get("boundary_policy").toString()
        List<Map<String, Object>> allCellAssignments = []
        List<Map<String, Object>> selectedCellAssignments = []
        Map<String, Integer> exclusionCounts = new TreeMap<>()
        for (def cell : newDetections) {
            Map<String, Object> assignment = assignCellToAnnotation(
                cell,
                selectedAnnotations,
                annotationByObject,
                boundaryPolicy
            )
            allCellAssignments.add(assignment)
            if (assignment.get("include") == Boolean.TRUE) {
                selectedCellAssignments.add(assignment)
            } else {
                String reason = assignment.get("exclusion_reason").toString()
                exclusionCounts.put(
                    reason,
                    (exclusionCounts.get(reason) ?: 0) + 1
                )
            }
        }

        Map<String, Object> imageManifest = buildImageManifest(
            imageConfig,
            imageRuntime,
            scriptSha256,
            configCanonicalSha256
        )
        Map<String, Object> channelManifest = buildChannelManifest(
            channelConfig,
            imageId,
            scriptSha256
        )
        Map<String, Object> annotationManifest = buildAnnotationManifest(
            annotationConfig,
            imageId,
            coordinateSpace.get("coordinate_space_id").toString(),
            annotationByObject.values().toList(),
            scriptSha256
        )
        Map<String, Object> segmentationManifest =
            buildSegmentationManifest(
                segmentationConfig,
                imageId,
                channelMapId,
                annotationSetId,
                coordinateSpace.get("coordinate_space_id").toString(),
                scriptSha256,
                configCanonicalSha256,
                selectedCellAssignments.size(),
                exclusionCounts,
                pluginStartedAt,
                pluginCompletedAt
            )

        Map<String, Object> mappings = requireMap(
            config.get("measurement_mappings"),
            "measurement_mappings"
        )
        Map<String, Object> qcConfig = requireMap(
            config.get("qc"),
            "qc"
        )
        List<Map<String, Object>> drafts = []
        for (Map<String, Object> assignment : selectedCellAssignments) {
            def cell = assignment.get("cell")
            def annotation = assignment.get("annotation")
            drafts.add(
                buildCellDraft(
                    cell,
                    annotationByObject.get(annotation),
                    packageId,
                    imageId,
                    biologicalUnitId,
                    segmentationRunId,
                    coordinateSpace.get("coordinate_space_id").toString(),
                    pixelCalibration,
                    mappings,
                    qcConfig,
                    provenanceConfig,
                    scriptSha256
                )
            )
        }
        drafts.sort { left, right ->
            int comparison = left.get("annotation_id").toString() <=>
                right.get("annotation_id").toString()
            if (comparison != 0) return comparison
            comparison = (
                (left.get("cell_y") as Number).doubleValue() <=>
                (right.get("cell_y") as Number).doubleValue()
            )
            if (comparison != 0) return comparison
            comparison = (
                (left.get("cell_x") as Number).doubleValue() <=>
                (right.get("cell_x") as Number).doubleValue()
            )
            if (comparison != 0) return comparison
            return left.get("cell_wkt").toString() <=>
                right.get("cell_wkt").toString()
        }

        List<Map<String, Object>> cellRecords = []
        Set<String> objectIds = new HashSet<>()
        Map<Object, String> acceptedObjectIdByCell = new IdentityHashMap<>()
        for (int index = 0; index < drafts.size(); index++) {
            Map<String, Object> draft = drafts.get(index)
            Map<String, Object> record =
                (Map<String, Object>) draft.get("record")
            record.put("object_index", index)
            String objectId = record.get("object_id").toString()
            if (!objectIds.add(objectId)) {
                fail("duplicate deterministic object_id " + objectId)
            }
            def draftCell = draft.get("cell")
            if (draftCell == null ||
                acceptedObjectIdByCell.put(draftCell, objectId) != null) {
                fail("duplicate or missing accepted candidate identity")
            }
            cellRecords.add(record)
        }
        Map<String, Integer> objectQcFlagCounts =
            countObjectQcFlags(cellRecords)
        Map<String, Object> candidateLedger = buildCandidateDispositionLedger(
            allCellAssignments,
            annotationByObject,
            acceptedObjectIdByCell,
            packageId,
            imageId,
            annotationSetId,
            segmentationRunId,
            coordinateSpace.get("coordinate_space_id").toString()
        )
        List<Map<String, Object>> candidateRecords = typedMapList(
            requireList(
                candidateLedger.get("records"),
                "generated candidate disposition records"
            ),
            "generated candidate disposition records"
        )
        if (candidateRecords.size() != newDetections.size()) {
            fail("candidate disposition ledger does not account for every new detection")
        }

        List<Path> published = []
        try {
            publishJson(outputDirectory, IMAGE_MANIFEST_PATH, imageManifest, published)
            publishJson(outputDirectory, CHANNEL_MANIFEST_PATH, channelManifest, published)
            publishJson(outputDirectory, ANNOTATION_MANIFEST_PATH, annotationManifest, published)
            publishJson(outputDirectory, SEGMENTATION_MANIFEST_PATH, segmentationManifest, published)
            publishJson(
                outputDirectory,
                methodBinding.get("definition_relative_path").toString(),
                (Map<String, Object>) methodBinding.get("definition"),
                published
            )
            publishJson(
                outputDirectory,
                methodBinding.get("parameter_set_relative_path").toString(),
                (Map<String, Object>) methodBinding.get("parameter_set"),
                published
            )

            Path cellsPath = packageRelativePath(outputDirectory, CELL_OBJECTS_PATH)
            ensureParentDirectory(cellsPath)
            String cellsSha256 = writeJsonLinesAtomic(cellsPath, cellRecords)
            published.add(cellsPath)

            Path candidateDispositionsPath = packageRelativePath(
                outputDirectory,
                CANDIDATE_DISPOSITIONS_PATH
            )
            ensureParentDirectory(candidateDispositionsPath)
            String candidateDispositionsSha256 = writeJsonLinesAtomic(
                candidateDispositionsPath,
                candidateRecords
            )
            published.add(candidateDispositionsPath)
            Map<String, Object> candidateManifest =
                buildCandidateDispositionManifest(
                    packageId,
                    imageId,
                    annotationSetId,
                    segmentationRunId,
                    coordinateSpace.get("coordinate_space_id").toString(),
                    candidateRecords.size(),
                    Files.size(candidateDispositionsPath),
                    candidateDispositionsSha256,
                    (Map<String, Integer>) candidateLedger.get("disposition_counts"),
                    (Map<String, Integer>) candidateLedger.get("reason_counts"),
                    (Map<String, Integer>) candidateLedger.get("geometry_warning_counts"),
                    scriptSha256,
                    configCanonicalSha256,
                    requireSha256(
                        requireMap(
                            imageConfig.get("source_artifact"),
                            "image.source_artifact"
                        ).get("sha256"),
                        "image.source_artifact.sha256"
                    ),
                    annotationContentSha256
                )
            publishJson(
                outputDirectory,
                CANDIDATE_DISPOSITIONS_MANIFEST_PATH,
                candidateManifest,
                published
            )

            Map<String, Object> packageDocument = buildPackage(
                packageConfig,
                imageManifest,
                channelManifest,
                annotationManifest,
                segmentationManifest,
                methodBinding,
                pixelCalibration,
                coordinateSpace,
                cellRecords.size(),
                Files.size(cellsPath),
                cellsSha256,
                qcConfig,
                provenanceConfig,
                configCanonicalSha256,
                objectQcFlagCounts,
                exclusionCounts
            )
            publishJson(outputDirectory, PACKAGE_PATH, packageDocument, published)
        } catch (Throwable failure) {
            for (Path path : published.reverse()) {
                Files.deleteIfExists(path)
            }
            throw failure
        }

        println canonicalJson([
            status: "exported_" + PILOT_STATUS,
            package_path: outputDirectory.resolve(PACKAGE_PATH).toString(),
            object_count: cellRecords.size(),
            candidate_count: candidateRecords.size(),
            candidate_disposition_counts: candidateLedger.get("disposition_counts"),
            object_qc_flag_counts: objectQcFlagCounts,
            excluded_cell_counts: exclusionCounts,
            scientific_validation: false,
            backend_equivalence: false,
            model_universality: false,
            authorization: "none",
            config_file_sha256: configFileSha256
        ])
    }

    static void validateConfig(Map<String, Object> config) {
        exactKeys(
            config,
            [
                "schema_version", "pilot_status", "output_directory", "package",
                "image", "channel_map", "annotation_set", "segmentation",
                "measurement_method", "measurement_mappings", "qc", "execution",
                "provenance"
            ],
            "configuration"
        )
        requireExactString(config.get("schema_version"), CONFIG_SCHEMA, "schema_version")
        requireExactString(config.get("pilot_status"), PILOT_STATUS, "pilot_status")
        requireResolvedString(config.get("output_directory"), "output_directory")

        Map<String, Object> packageConfig = requireMap(config.get("package"), "package")
        exactKeys(packageConfig, ["package_id", "parent_package_id"], "package")
        requireIdentifier(packageConfig.get("package_id"), "package.package_id")
        requireNullableIdentifier(packageConfig.get("parent_package_id"), "package.parent_package_id")

        Map<String, Object> image = requireMap(config.get("image"), "image")
        exactKeys(
            image,
            [
                "image_id", "biological_unit_id", "expected_server_name",
                "source_artifact", "calibration", "coordinate_space_id",
                "acquisition", "provenance"
            ],
            "image"
        )
        requireIdentifier(image.get("image_id"), "image.image_id")
        requireIdentifier(image.get("biological_unit_id"), "image.biological_unit_id")
        requireResolvedString(image.get("expected_server_name"), "image.expected_server_name")
        Map<String, Object> source = requireMap(image.get("source_artifact"), "image.source_artifact")
        exactKeys(source, ["source_uri", "sha256", "size_bytes", "media_type"], "image.source_artifact")
        String sourceUri = requireResolvedString(source.get("source_uri"), "image.source_artifact.source_uri")
        try {
            URI uri = new URI(sourceUri)
            if (!uri.isAbsolute()) fail("image.source_artifact.source_uri must be absolute")
        } catch (Exception error) {
            fail("image.source_artifact.source_uri is invalid")
        }
        requireSha256(source.get("sha256"), "image.source_artifact.sha256")
        requireNonnegativeSafeLong(source.get("size_bytes"), "image.source_artifact.size_bytes")
        requireResolvedString(source.get("media_type"), "image.source_artifact.media_type")
        Map<String, Object> calibration = requireMap(image.get("calibration"), "image.calibration")
        exactKeys(
            calibration,
            ["calibration_id", "expected_pixel_width_um", "expected_pixel_height_um", "tolerance_um"],
            "image.calibration"
        )
        requireIdentifier(calibration.get("calibration_id"), "image.calibration.calibration_id")
        requirePositiveDouble(calibration.get("expected_pixel_width_um"), "image.calibration.expected_pixel_width_um")
        requirePositiveDouble(calibration.get("expected_pixel_height_um"), "image.calibration.expected_pixel_height_um")
        requirePositiveDouble(calibration.get("tolerance_um"), "image.calibration.tolerance_um")
        requireIdentifier(image.get("coordinate_space_id"), "image.coordinate_space_id")
        Map<String, Object> acquisition = requireMap(image.get("acquisition"), "image.acquisition")
        exactKeys(
            acquisition,
            ["mouse_id", "specimen_id", "section_id", "slide_id", "batch_id", "scanner_id", "acquired_at"],
            "image.acquisition"
        )
        for (String key : ["mouse_id", "specimen_id", "section_id", "slide_id", "batch_id", "scanner_id"]) {
            requireNullableIdentifier(acquisition.get(key), "image.acquisition." + key)
        }
        requireNullableTimestamp(acquisition.get("acquired_at"), "image.acquisition.acquired_at")
        validateProducerProvenance(requireMap(image.get("provenance"), "image.provenance"), "image.provenance")

        Map<String, Object> channelMap = requireMap(config.get("channel_map"), "channel_map")
        exactKeys(channelMap, ["channel_map_id", "channels", "provenance"], "channel_map")
        requireIdentifier(channelMap.get("channel_map_id"), "channel_map.channel_map_id")
        List<Map<String, Object>> channels = typedMapList(
            requireList(channelMap.get("channels"), "channel_map.channels"),
            "channel_map.channels"
        )
        if (channels.isEmpty()) fail("channel_map.channels must not be empty")
        Set<String> channelIds = new HashSet<>()
        Set<Integer> sourceIndices = new HashSet<>()
        int previousIndex = -1
        for (int index = 0; index < channels.size(); index++) {
            Map<String, Object> channel = channels.get(index)
            String context = "channel_map.channels[" + index + "]"
            exactKeys(
                channel,
                ["source_channel_index", "source_channel_name", "channel_id", "marker_id", "role", "intensity"],
                context
            )
            int sourceIndex = requireInteger(channel.get("source_channel_index"), context + ".source_channel_index", 0)
            if (sourceIndex <= previousIndex) fail("channel_map.channels must be sorted by source index")
            previousIndex = sourceIndex
            if (!sourceIndices.add(sourceIndex)) fail("duplicate source channel index " + sourceIndex)
            requireResolvedString(channel.get("source_channel_name"), context + ".source_channel_name")
            String channelId = requireIdentifier(channel.get("channel_id"), context + ".channel_id")
            if (!channelIds.add(channelId)) fail("duplicate channel_id " + channelId)
            requireIdentifier(channel.get("marker_id"), context + ".marker_id")
            requireEnum(channel.get("role"), ["nuclear_counterstain", "biomarker", "autofluorescence", "other"], context + ".role")
            validateIntensityDescriptor(requireMap(channel.get("intensity"), context + ".intensity"), context + ".intensity")
        }
        validateProducerProvenance(requireMap(channelMap.get("provenance"), "channel_map.provenance"), "channel_map.provenance")

        Map<String, Object> annotations = requireMap(config.get("annotation_set"), "annotation_set")
        exactKeys(
            annotations,
            ["annotation_set_id", "revision", "classification", "expected_content_sha256", "provenance"],
            "annotation_set"
        )
        requireIdentifier(annotations.get("annotation_set_id"), "annotation_set.annotation_set_id")
        requireNonnegativeSafeLong(annotations.get("revision"), "annotation_set.revision")
        requireResolvedString(annotations.get("classification"), "annotation_set.classification")
        requireSha256(annotations.get("expected_content_sha256"), "annotation_set.expected_content_sha256")
        Map<String, Object> annotationProvenance = requireMap(annotations.get("provenance"), "annotation_set.provenance")
        exactKeys(
            annotationProvenance,
            ["created_at", "source_system", "producer_id", "producer_version", "parent_annotation_set_id"],
            "annotation_set.provenance"
        )
        requireTimestamp(annotationProvenance.get("created_at"), "annotation_set.provenance.created_at")
        requireExactString(annotationProvenance.get("source_system"), "qupath", "annotation_set.provenance.source_system")
        requireIdentifier(annotationProvenance.get("producer_id"), "annotation_set.provenance.producer_id")
        requireSemver(annotationProvenance.get("producer_version"), "annotation_set.provenance.producer_version")
        requireNullableIdentifier(annotationProvenance.get("parent_annotation_set_id"), "annotation_set.provenance.parent_annotation_set_id")

        validateSegmentation(requireMap(config.get("segmentation"), "segmentation"), channels)
        validateMeasurementMethodConfig(requireMap(config.get("measurement_method"), "measurement_method"))
        validateMeasurementMappings(requireMap(config.get("measurement_mappings"), "measurement_mappings"), channels)
        Map<String, Object> qc = requireMap(config.get("qc"), "qc")
        exactKeys(qc, ["object_default_status", "object_default_flags", "package_flags"], "qc")
        requireExactString(qc.get("object_default_status"), "not_evaluated", "qc.object_default_status")
        validateQcFlags(requireList(qc.get("object_default_flags"), "qc.object_default_flags"), "qc.object_default_flags")
        validateQcFlags(requireList(qc.get("package_flags"), "qc.package_flags"), "qc.package_flags")

        Map<String, Object> execution = requireMap(config.get("execution"), "execution")
        exactKeys(
            execution,
            ["script_path", "expected_script_sha256", "script_contract", "script_version"],
            "execution"
        )
        requireResolvedString(execution.get("script_path"), "execution.script_path")
        requireSha256(execution.get("expected_script_sha256"), "execution.expected_script_sha256")
        requireExactString(execution.get("script_contract"), SCRIPT_CONTRACT, "execution.script_contract")
        requireExactString(execution.get("script_version"), SCRIPT_VERSION, "execution.script_version")

        Map<String, Object> provenance = requireMap(config.get("provenance"), "provenance")
        exactKeys(
            provenance,
            ["created_at", "exporter_id", "exporter_version", "code_revision"],
            "provenance"
        )
        requireTimestamp(provenance.get("created_at"), "provenance.created_at")
        requireIdentifier(provenance.get("exporter_id"), "provenance.exporter_id")
        requireSemver(provenance.get("exporter_version"), "provenance.exporter_version")
        requireCodeRevision(provenance.get("code_revision"), "provenance.code_revision")
    }

    static void validateSegmentation(
        Map<String, Object> segmentation,
        List<Map<String, Object>> channels
    ) {
        exactKeys(
            segmentation,
            [
                "segmentation_run_id", "backend", "detector", "plugin_class",
                "parameters", "model", "preprocessing", "boundary_policy",
                "qc", "provenance"
            ],
            "segmentation"
        )
        requireIdentifier(segmentation.get("segmentation_run_id"), "segmentation.segmentation_run_id")
        Map<String, Object> backend = requireMap(segmentation.get("backend"), "segmentation.backend")
        exactKeys(backend, ["kind", "name", "version", "artifact_sha256"], "segmentation.backend")
        String kind = requireEnum(backend.get("kind"), ["native_qupath", "stardist", "instanseg"], "segmentation.backend.kind")
        if (kind == "stardist" || kind == "instanseg") {
            fail("CANDIDATE_BACKEND_NOT_IMPLEMENTED: " + kind + " is not implemented by this script")
        }
        requireResolvedString(backend.get("name"), "segmentation.backend.name")
        requireSemver(backend.get("version"), "segmentation.backend.version")
        requireSha256(backend.get("artifact_sha256"), "segmentation.backend.artifact_sha256")
        Map<String, Object> detector = requireMap(segmentation.get("detector"), "segmentation.detector")
        exactKeys(detector, ["detector_id", "detector_version"], "segmentation.detector")
        requireIdentifier(detector.get("detector_id"), "segmentation.detector.detector_id")
        requireSemver(detector.get("detector_version"), "segmentation.detector.detector_version")
        requireExactString(segmentation.get("plugin_class"), WATERSHED_PLUGIN, "segmentation.plugin_class")
        Map<String, Object> parameters = requireMap(segmentation.get("parameters"), "segmentation.parameters")
        exactKeys(
            parameters,
            [
                "detectionImage", "requestedPixelSizeMicrons",
                "backgroundRadiusMicrons", "backgroundByReconstruction",
                "medianRadiusMicrons", "sigmaMicrons", "minAreaMicrons",
                "maxAreaMicrons", "threshold", "watershedPostProcess",
                "cellExpansionMicrons", "includeNuclei", "smoothBoundaries",
                "makeMeasurements"
            ],
            "segmentation.parameters"
        )
        String detectionImage = requireResolvedString(parameters.get("detectionImage"), "segmentation.parameters.detectionImage")
        if (!channels.any { it.get("source_channel_name") == detectionImage }) {
            fail("detectionImage must equal a configured source channel name")
        }
        requirePositiveDouble(parameters.get("requestedPixelSizeMicrons"), "segmentation.parameters.requestedPixelSizeMicrons")
        for (String key : ["backgroundRadiusMicrons", "medianRadiusMicrons", "sigmaMicrons"]) {
            requireNonnegativeDouble(parameters.get(key), "segmentation.parameters." + key)
        }
        requirePositiveDouble(
            parameters.get("cellExpansionMicrons"),
            "segmentation.parameters.cellExpansionMicrons"
        )
        double minimumArea = requirePositiveDouble(parameters.get("minAreaMicrons"), "segmentation.parameters.minAreaMicrons")
        double maximumArea = requirePositiveDouble(parameters.get("maxAreaMicrons"), "segmentation.parameters.maxAreaMicrons")
        if (maximumArea < minimumArea) fail("maxAreaMicrons must be at least minAreaMicrons")
        finiteDouble(parameters.get("threshold"), "segmentation.parameters.threshold")
        for (String key : ["backgroundByReconstruction", "watershedPostProcess", "includeNuclei", "smoothBoundaries", "makeMeasurements"]) {
            requireBoolean(parameters.get(key), "segmentation.parameters." + key)
        }
        if (parameters.get("includeNuclei") != Boolean.TRUE || parameters.get("makeMeasurements") != Boolean.TRUE) {
            fail("includeNuclei and makeMeasurements must both be true")
        }

        Map<String, Object> model = requireMap(segmentation.get("model"), "segmentation.model")
        exactKeys(model, ["model_id", "model_version", "descriptor_sha256", "weights_sha256"], "segmentation.model")
        requireIdentifier(model.get("model_id"), "segmentation.model.model_id")
        requireSemver(model.get("model_version"), "segmentation.model.model_version")
        requireSha256(model.get("descriptor_sha256"), "segmentation.model.descriptor_sha256")
        if (model.get("weights_sha256") != null) fail("native_qupath model.weights_sha256 must be null")
        Map<String, Object> preprocessing = requireMap(segmentation.get("preprocessing"), "segmentation.preprocessing")
        exactKeys(preprocessing, ["profile_id", "profile_sha256"], "segmentation.preprocessing")
        requireIdentifier(preprocessing.get("profile_id"), "segmentation.preprocessing.profile_id")
        requireSha256(preprocessing.get("profile_sha256"), "segmentation.preprocessing.profile_sha256")
        String boundaryPolicy = requireEnum(
            segmentation.get("boundary_policy"),
            ["clip_to_annotation", "exclude_touching_annotation_boundary", "include_touching_annotation_boundary"],
            "segmentation.boundary_policy"
        )
        if (boundaryPolicy != "exclude_touching_annotation_boundary") {
            fail(
                "CANDIDATE_BOUNDARY_POLICY_NOT_IMPLEMENTED: " + boundaryPolicy +
                " would require clipping or accepting boundary-touching geometry; " +
                "this POC supports exclude_touching_annotation_boundary only"
            )
        }
        Map<String, Object> segmentationQc = requireMap(
            segmentation.get("qc"),
            "segmentation.qc"
        )
        validateRunQc(segmentationQc, "segmentation.qc")
        requireExactString(
            segmentationQc.get("status"),
            "not_evaluated",
            "segmentation.qc.status"
        )
        Map<String, Object> provenance = requireMap(segmentation.get("provenance"), "segmentation.provenance")
        exactKeys(
            provenance,
            ["created_at", "producer_id", "producer_version", "code_revision", "runtime_sha256"],
            "segmentation.provenance"
        )
        requireTimestamp(provenance.get("created_at"), "segmentation.provenance.created_at")
        requireIdentifier(provenance.get("producer_id"), "segmentation.provenance.producer_id")
        requireSemver(provenance.get("producer_version"), "segmentation.provenance.producer_version")
        requireCodeRevision(provenance.get("code_revision"), "segmentation.provenance.code_revision")
        requireSha256(provenance.get("runtime_sha256"), "segmentation.provenance.runtime_sha256")
    }

    static void validateMeasurementMethodConfig(Map<String, Object> method) {
        exactKeys(
            method,
            [
                "definition_source_path", "definition_output_relative_path",
                "expected_definition_sha256", "parameter_set_source_path",
                "parameter_set_output_relative_path",
                "expected_parameter_set_sha256", "expected_method_instance_sha256"
            ],
            "measurement_method"
        )
        requireResolvedString(method.get("definition_source_path"), "measurement_method.definition_source_path")
        requireSafeRelativePath(method.get("definition_output_relative_path"), "measurement_method.definition_output_relative_path")
        requireSha256(method.get("expected_definition_sha256"), "measurement_method.expected_definition_sha256")
        requireResolvedString(method.get("parameter_set_source_path"), "measurement_method.parameter_set_source_path")
        requireSafeRelativePath(method.get("parameter_set_output_relative_path"), "measurement_method.parameter_set_output_relative_path")
        requireSha256(method.get("expected_parameter_set_sha256"), "measurement_method.expected_parameter_set_sha256")
        requireSha256(method.get("expected_method_instance_sha256"), "measurement_method.expected_method_instance_sha256")
        if (method.get("definition_output_relative_path") == method.get("parameter_set_output_relative_path")) {
            fail("measurement method output paths must differ")
        }
        Set<String> reserved = [
            PACKAGE_PATH,
            CELL_OBJECTS_PATH,
            IMAGE_MANIFEST_PATH,
            CHANNEL_MANIFEST_PATH,
            ANNOTATION_MANIFEST_PATH,
            SEGMENTATION_MANIFEST_PATH
        ].toSet()
        for (String key : ["definition_output_relative_path", "parameter_set_output_relative_path"]) {
            String path = method.get(key).toString()
            if (!path.startsWith("contracts/") || reserved.contains(path)) {
                fail("measurement_method." + key + " must be a non-reserved contracts/ path")
            }
        }
    }

    static void validateMeasurementMappings(
        Map<String, Object> mappings,
        List<Map<String, Object>> channels
    ) {
        exactKeys(mappings, ["morphology", "intensity"], "measurement_mappings")
        List<Map<String, Object>> morphology = typedMapList(
            requireList(mappings.get("morphology"), "measurement_mappings.morphology"),
            "measurement_mappings.morphology"
        )
        List<Map<String, Object>> intensity = typedMapList(
            requireList(mappings.get("intensity"), "measurement_mappings.intensity"),
            "measurement_mappings.intensity"
        )
        if (morphology.isEmpty() || intensity.isEmpty()) {
            fail("morphology and intensity mappings must both be nonempty")
        }
        Set<String> measurementIds = new HashSet<>()
        for (int index = 0; index < morphology.size(); index++) {
            Map<String, Object> mapping = morphology.get(index)
            String context = "measurement_mappings.morphology[" + index + "]"
            exactKeys(mapping, ["measurement_id", "compartment", "feature", "unit"], context)
            String id = requireIdentifier(mapping.get("measurement_id"), context + ".measurement_id")
            if (!measurementIds.add(id)) fail("duplicate measurement_id " + id)
            String compartment = requireEnum(mapping.get("compartment"), ["cell", "nucleus"], context + ".compartment")
            String feature = requireEnum(mapping.get("feature"), ["area", "perimeter", "circularity", "nucleus_cell_area_ratio"], context + ".feature")
            String unit = requireEnum(mapping.get("unit"), ["um2", "um", "ratio"], context + ".unit")
            validateMorphologyCombination(compartment, feature, unit, context)
        }
        Map<String, Map<String, Object>> channelsById = [:]
        for (Map<String, Object> channel : channels) {
            channelsById.put(channel.get("channel_id").toString(), channel)
        }
        for (int index = 0; index < intensity.size(); index++) {
            Map<String, Object> mapping = intensity.get(index)
            String context = "measurement_mappings.intensity[" + index + "]"
            exactKeys(
                mapping,
                ["measurement_id", "source_measurement", "channel_id", "marker_id", "compartment", "statistic", "unit"],
                context
            )
            String id = requireIdentifier(mapping.get("measurement_id"), context + ".measurement_id")
            if (!measurementIds.add(id)) fail("duplicate measurement_id " + id)
            requireResolvedString(mapping.get("source_measurement"), context + ".source_measurement")
            String channelId = requireIdentifier(mapping.get("channel_id"), context + ".channel_id")
            Map<String, Object> channel = channelsById.get(channelId)
            if (channel == null) fail(context + " refers to unknown channel_id")
            String markerId = requireIdentifier(mapping.get("marker_id"), context + ".marker_id")
            if (markerId != channel.get("marker_id")) fail(context + " marker_id disagrees with channel map")
            requireEnum(mapping.get("compartment"), ["cell", "nucleus", "cytoplasm"], context + ".compartment")
            String statistic = requireEnum(
                mapping.get("statistic"),
                ["mean", "median", "minimum", "maximum", "standard_deviation", "sum"],
                context + ".statistic"
            )
            String unit = requireEnum(
                mapping.get("unit"),
                ["native_sample_value", "normalized_intensity", "integrated_native_sample_value"],
                context + ".unit"
            )
            String channelUnit = requireMap(channel.get("intensity"), context + ".channel.intensity").get("unit").toString()
            if (statistic == "sum") {
                if (unit != "integrated_native_sample_value") fail(context + " sum requires integrated unit")
            } else if (unit != channelUnit) {
                fail(context + " unit disagrees with channel mapping")
            }
        }
    }

    static Map<String, Object> loadMeasurementMethod(
        Path configPath,
        Map<String, Object> methodConfig,
        Map<String, Object> mappings,
        List<Map<String, Object>> channels
    ) {
        Path definitionPath = resolveInputPath(configPath, methodConfig.get("definition_source_path").toString())
        Path parameterPath = resolveInputPath(configPath, methodConfig.get("parameter_set_source_path").toString())
        Map<String, Object> definition = loadStrictObject(definitionPath, "measurement definition")
        Map<String, Object> parameterSet = loadStrictObject(parameterPath, "parameter set")
        validateDefinition(definition)
        validateParameterSet(parameterSet)
        String definitionSha = canonicalSha256(definition)
        String parameterSha = canonicalSha256(parameterSet)
        if (definitionSha != methodConfig.get("expected_definition_sha256")) fail("measurement definition hash mismatch")
        if (parameterSha != methodConfig.get("expected_parameter_set_sha256")) fail("measurement parameter-set hash mismatch")
        Map<String, Object> definitionReference = requireMap(
            parameterSet.get("measurement_definition"),
            "parameter_set.measurement_definition"
        )
        if (definitionReference.get("definition_id") != definition.get("definition_id") ||
            definitionReference.get("definition_version") != definition.get("definition_version") ||
            definitionReference.get("canonical_sha256") != definitionSha) {
            fail("parameter set does not bind the loaded definition")
        }
        validateParameterBindings(definition, parameterSet)
        String methodInstanceSha = canonicalSha256([
            contract: METHOD_INSTANCE_DOMAIN,
            definition_sha256: definitionSha,
            parameter_set_sha256: parameterSha
        ])
        if (methodInstanceSha != methodConfig.get("expected_method_instance_sha256")) {
            fail("measurement method-instance hash mismatch")
        }
        validateFeaturesAgainstMappings(definition, mappings, channels)
        return [
            definition: definition,
            parameter_set: parameterSet,
            definition_id: definition.get("definition_id"),
            definition_sha256: definitionSha,
            definition_relative_path: methodConfig.get("definition_output_relative_path"),
            parameter_set_id: parameterSet.get("parameter_set_id"),
            parameter_set_sha256: parameterSha,
            parameter_set_relative_path: methodConfig.get("parameter_set_output_relative_path"),
            method_instance_sha256: methodInstanceSha
        ]
    }

    static void validateDefinition(Map<String, Object> definition) {
        exactKeys(
            definition,
            [
                "\$schema", "schema_version", "contract_type", "definition_id",
                "definition_version", "object_type", "dimensionality",
                "semantic_inputs", "parameter_slots", "features",
                "missingness", "aggregation"
            ],
            "measurement_definition"
        )
        requireExactString(definition.get("\$schema"), DEFINITION_SCHEMA, "measurement_definition.\$schema")
        requireExactString(definition.get("schema_version"), CONTRACT_VERSION, "measurement_definition.schema_version")
        requireExactString(definition.get("contract_type"), "ifquant_platform_measurement_definition", "measurement_definition.contract_type")
        requireIdentifier(definition.get("definition_id"), "measurement_definition.definition_id")
        requireSemver(definition.get("definition_version"), "measurement_definition.definition_version")
        requireExactString(definition.get("object_type"), "cell", "measurement_definition.object_type")
        requireExactString(definition.get("dimensionality"), "2d", "measurement_definition.dimensionality")
        List<Map<String, Object>> inputs = typedMapList(
            requireList(definition.get("semantic_inputs"), "measurement_definition.semantic_inputs"),
            "measurement_definition.semantic_inputs"
        )
        Set<String> inputIds = new HashSet<>()
        for (int index = 0; index < inputs.size(); index++) {
            Map<String, Object> input = inputs.get(index)
            String context = "measurement_definition.semantic_inputs[" + index + "]"
            exactKeys(input, ["input_id", "marker_id", "intensity_coordinate", "intensity_representation", "intensity_transform"], context)
            String id = requireIdentifier(input.get("input_id"), context + ".input_id")
            if (!inputIds.add(id)) fail("duplicate semantic input " + id)
            requireIdentifier(input.get("marker_id"), context + ".marker_id")
            requireEnum(input.get("intensity_coordinate"), ["native_sample_value", "normalized_unit_interval"], context + ".intensity_coordinate")
            requireEnum(input.get("intensity_representation"), ["unsigned_integer", "floating_point"], context + ".intensity_representation")
            requireEnum(input.get("intensity_transform"), ["none", "linear_rescale", "log1p"], context + ".intensity_transform")
        }
        List<Map<String, Object>> slots = typedMapList(
            requireList(definition.get("parameter_slots"), "measurement_definition.parameter_slots"),
            "measurement_definition.parameter_slots"
        )
        if (!slots.isEmpty()) {
            fail(
                "this engineering POC supports measurement definitions with " +
                "no parameter slots; governed constrained slots remain a Python concern"
            )
        }
        Set<String> slotIds = new HashSet<>()
        List<Map<String, Object>> features = typedMapList(
            requireList(definition.get("features"), "measurement_definition.features"),
            "measurement_definition.features"
        )
        if (features.isEmpty()) fail("measurement definition has no features")
        Set<String> featureIds = new HashSet<>()
        for (int index = 0; index < features.size(); index++) {
            Map<String, Object> feature = features.get(index)
            String context = "measurement_definition.features[" + index + "]"
            exactKeys(
                feature,
                ["feature_id", "feature_kind", "compartment", "statistic", "unit", "source", "input_id", "parameter_ids"],
                context
            )
            String id = requireIdentifier(feature.get("feature_id"), context + ".feature_id")
            if (!featureIds.add(id)) fail("duplicate feature " + id)
            String kind = requireEnum(feature.get("feature_kind"), ["morphology", "intensity"], context + ".feature_kind")
            requireEnum(feature.get("compartment"), ["cell", "cytoplasm", "membrane", "nucleus"], context + ".compartment")
            requireIdentifier(feature.get("statistic"), context + ".statistic")
            requireIdentifier(feature.get("unit"), context + ".unit")
            String source = requireEnum(feature.get("source"), ["geometry", "semantic_input"], context + ".source")
            if (kind == "morphology") {
                if (source != "geometry" || feature.get("input_id") != null) fail(context + " morphology source/input is inconsistent")
            } else {
                if (source != "semantic_input" || !inputIds.contains(feature.get("input_id"))) {
                    fail(context + " intensity source/input is inconsistent")
                }
            }
            List parameterIds = requireList(feature.get("parameter_ids"), context + ".parameter_ids")
            Set<String> used = new HashSet<>()
            for (Object parameterId : parameterIds) {
                String validated = requireIdentifier(parameterId, context + ".parameter_ids")
                if (!slotIds.contains(validated) || !used.add(validated)) fail(context + " has invalid parameter_ids")
            }
        }
        Map<String, Object> missingness = requireMap(definition.get("missingness"), "measurement_definition.missingness")
        exactKeys(missingness, ["unavailable", "nonfinite"], "missingness")
        requireExactString(missingness.get("unavailable"), "reject_package", "missingness.unavailable")
        requireExactString(missingness.get("nonfinite"), "reject", "missingness.nonfinite")
        Map<String, Object> aggregation = requireMap(definition.get("aggregation"), "measurement_definition.aggregation")
        exactKeys(aggregation, ["method"], "aggregation")
        requireEnum(aggregation.get("method"), ["none", "sum", "ratio_of_sums"], "aggregation.method")
    }

    static void validateParameterSet(Map<String, Object> parameterSet) {
        exactKeys(
            parameterSet,
            [
                "\$schema", "schema_version", "contract_type", "parameter_set_id",
                "parameter_set_version", "measurement_definition", "scope", "values"
            ],
            "parameter_set"
        )
        requireExactString(parameterSet.get("\$schema"), PARAMETER_SCHEMA, "parameter_set.\$schema")
        requireExactString(parameterSet.get("schema_version"), CONTRACT_VERSION, "parameter_set.schema_version")
        requireExactString(parameterSet.get("contract_type"), "ifquant_platform_parameter_set", "parameter_set.contract_type")
        requireIdentifier(parameterSet.get("parameter_set_id"), "parameter_set.parameter_set_id")
        requireSemver(parameterSet.get("parameter_set_version"), "parameter_set.parameter_set_version")
        Map<String, Object> reference = requireMap(parameterSet.get("measurement_definition"), "parameter_set.measurement_definition")
        exactKeys(reference, ["definition_id", "definition_version", "canonical_sha256"], "parameter_set.measurement_definition")
        requireIdentifier(reference.get("definition_id"), "parameter_set.measurement_definition.definition_id")
        requireSemver(reference.get("definition_version"), "parameter_set.measurement_definition.definition_version")
        requireSha256(reference.get("canonical_sha256"), "parameter_set.measurement_definition.canonical_sha256")
        Map<String, Object> scope = requireMap(parameterSet.get("scope"), "parameter_set.scope")
        exactKeys(scope, ["scope_id", "binding", "scope_profile_sha256", "transfer_policy"], "parameter_set.scope")
        requireIdentifier(scope.get("scope_id"), "parameter_set.scope.scope_id")
        String binding = requireEnum(scope.get("binding"), ["content_addressed", "identifier_only_unattested"], "parameter_set.scope.binding")
        if (binding == "content_addressed") {
            requireSha256(scope.get("scope_profile_sha256"), "parameter_set.scope.scope_profile_sha256")
        } else if (scope.get("scope_profile_sha256") != null) {
            fail("identifier-only scope must have null profile hash")
        }
        requireExactString(scope.get("transfer_policy"), "declared_scope_only", "parameter_set.scope.transfer_policy")
        List<Map<String, Object>> values = typedMapList(
            requireList(parameterSet.get("values"), "parameter_set.values"),
            "parameter_set.values"
        )
        Set<String> ids = new HashSet<>()
        for (int index = 0; index < values.size(); index++) {
            Map<String, Object> value = values.get(index)
            String context = "parameter_set.values[" + index + "]"
            exactKeys(value, ["parameter_id", "value", "unit"], context)
            String id = requireIdentifier(value.get("parameter_id"), context + ".parameter_id")
            if (!ids.add(id)) fail("duplicate parameter value " + id)
            if (!(value.get("value") instanceof Boolean || value.get("value") instanceof Number || value.get("value") instanceof String)) {
                fail(context + ".value has unsupported type")
            }
            canonicalize(value.get("value"))
            requireIdentifier(value.get("unit"), context + ".unit")
        }
    }

    static void validateParameterBindings(
        Map<String, Object> definition,
        Map<String, Object> parameterSet
    ) {
        Map<String, Map<String, Object>> slots = [:]
        for (Map<String, Object> slot : typedMapList(requireList(definition.get("parameter_slots"), "parameter_slots"), "parameter_slots")) {
            slots.put(slot.get("parameter_id").toString(), slot)
        }
        Map<String, Map<String, Object>> values = [:]
        for (Map<String, Object> value : typedMapList(requireList(parameterSet.get("values"), "parameter values"), "parameter values")) {
            values.put(value.get("parameter_id").toString(), value)
        }
        if (slots.keySet() != values.keySet()) fail("parameter set must bind all and only definition slots")
        for (String id : slots.keySet()) {
            Map<String, Object> slot = slots.get(id)
            Map<String, Object> value = values.get(id)
            if (slot.get("unit") != value.get("unit")) fail("parameter " + id + " has wrong unit")
            String type = slot.get("value_type").toString()
            Object actual = value.get("value")
            boolean integerValue = false
            if (actual instanceof Number && !(actual instanceof Boolean)) {
                try {
                    new BigDecimal(actual.toString()).toBigIntegerExact()
                    integerValue = true
                } catch (ArithmeticException ignored) {
                    integerValue = false
                }
            }
            boolean matches =
                (type == "boolean" && actual instanceof Boolean) ||
                (type == "integer" && integerValue) ||
                (type == "number" && actual instanceof Number && !(actual instanceof Boolean)) ||
                (type == "string" && actual instanceof String)
            if (!matches) fail("parameter " + id + " has wrong value type")
        }
    }

    static void validateFeaturesAgainstMappings(
        Map<String, Object> definition,
        Map<String, Object> mappings,
        List<Map<String, Object>> channels
    ) {
        Map<String, Map<String, Object>> byId = [:]
        for (Map<String, Object> mapping : typedMapList(requireList(mappings.get("morphology"), "morphology mappings"), "morphology mappings")) {
            byId.put(mapping.get("measurement_id").toString(), mapping)
        }
        for (Map<String, Object> mapping : typedMapList(requireList(mappings.get("intensity"), "intensity mappings"), "intensity mappings")) {
            byId.put(mapping.get("measurement_id").toString(), mapping)
        }
        List<Map<String, Object>> features = typedMapList(requireList(definition.get("features"), "definition features"), "definition features")
        Set<String> featureIds = features.collect { it.get("feature_id").toString() }.toSet()
        if (featureIds != byId.keySet()) fail("measurement mappings must cover all and only definition features")
        Map<String, Map<String, Object>> channelsById = [:]
        for (Map<String, Object> channel : channels) channelsById.put(channel.get("channel_id").toString(), channel)
        for (Map<String, Object> input : typedMapList(
            requireList(definition.get("semantic_inputs"), "definition semantic inputs"),
            "definition semantic inputs"
        )) {
            String inputId = input.get("input_id").toString()
            Map<String, Object> channel = channelsById.get(inputId)
            if (channel == null) {
                fail("semantic input " + inputId + " lacks an exact channel_id binding")
            }
            if (input.get("marker_id") != channel.get("marker_id")) {
                fail("semantic input " + inputId + " marker_id disagrees with channel map")
            }
            Map<String, Object> intensity = requireMap(
                channel.get("intensity"),
                "channel " + inputId + " intensity"
            )
            String expectedCoordinate = intensity.get("unit") == "native_sample_value" ?
                "native_sample_value" : "normalized_unit_interval"
            String expectedTransform = intensity.get("transform") == "none" ?
                "none" : "linear_rescale"
            if (input.get("intensity_coordinate") != expectedCoordinate ||
                input.get("intensity_representation") != intensity.get("representation") ||
                input.get("intensity_transform") != expectedTransform) {
                fail(
                    "semantic input " + inputId +
                    " intensity coordinate/representation/transform disagrees " +
                    "with the channel map"
                )
            }
        }
        Map<String, String> statisticCrosswalk = [
            stddev: "standard_deviation",
            integrated_intensity: "sum"
        ]
        for (Map<String, Object> feature : features) {
            String id = feature.get("feature_id").toString()
            Map<String, Object> mapping = byId.get(id)
            if (feature.get("compartment") != mapping.get("compartment")) fail("feature " + id + " compartment mismatch")
            if (feature.get("feature_kind") == "morphology") {
                if (feature.get("statistic") != mapping.get("feature")) fail("feature " + id + " morphology statistic mismatch")
                String definitionUnit = feature.get("unit").toString()
                String mappingUnit = mapping.get("unit").toString()
                if (definitionUnit != mappingUnit) {
                    fail("feature " + id + " morphology unit mismatch")
                }
            } else {
                String definitionStatistic = feature.get("statistic").toString()
                String objectStatistic = statisticCrosswalk.getOrDefault(
                    definitionStatistic,
                    definitionStatistic
                )
                if (objectStatistic != mapping.get("statistic") ||
                    feature.get("input_id") != mapping.get("channel_id") ||
                    feature.get("unit") != mapping.get("unit")) {
                    fail("feature " + id + " intensity mapping mismatch")
                }
                Map<String, Object> channel = channelsById.get(mapping.get("channel_id").toString())
                if (channel == null || channel.get("marker_id") != mapping.get("marker_id")) {
                    fail("feature " + id + " channel mapping mismatch")
                }
            }
        }
    }

    static Map<String, Object> verifyCurrentImage(
        def imageData,
        Map<String, Object> imageConfig,
        List<Map<String, Object>> channels
    ) {
        def server = imageData.getServer()
        int zPlanes = server.nZSlices()
        int timepoints = server.nTimepoints()
        if (zPlanes != 1 || timepoints != 1) {
            fail(
                "canonical v1 is singleton-plane 2D; current image has z_planes=" +
                zPlanes + " and timepoints=" + timepoints
            )
        }
        int widthPixels = server.getWidth()
        int heightPixels = server.getHeight()
        if (widthPixels <= 0 || heightPixels <= 0) {
            fail("current image dimensions must be positive")
        }
        String observedName = server.getMetadata().getName()
        String expectedName = imageConfig.get("expected_server_name").toString()
        if (observedName != expectedName) {
            fail("current image name mismatch: expected " + quoted(expectedName) + " but found " + quoted(observedName))
        }
        List observedUris = server.getURIs().collect { it.normalize() }.toList()
        if (observedUris.size() != 1) {
            fail("v1 source_artifact requires exactly one current-image URI; observed " + observedUris.size())
        }
        Map<String, Object> source = requireMap(imageConfig.get("source_artifact"), "image.source_artifact")
        URI configuredUri = new URI(source.get("source_uri").toString()).normalize()
        if (observedUris.get(0) != configuredUri) fail("configured source URI does not equal the current image URI")
        if (configuredUri.getScheme() != "file") fail("pilot can verify source bytes only for a file URI")
        Path sourcePath = Paths.get(configuredUri)
        if (!Files.isRegularFile(sourcePath)) fail("configured source URI is not a regular local file")
        long sourceSize = Files.size(sourcePath)
        if (sourceSize != (source.get("size_bytes") as Number).longValue()) fail("configured source size does not match source bytes")
        String sourceHash = sha256File(sourcePath)
        if (sourceHash != source.get("sha256")) fail("configured source SHA-256 does not match source bytes")

        List serverChannels = server.getMetadata().getChannels()
        def pixelType = server.getPixelType()
        if (pixelType == null) fail("current image pixel type is unavailable")
        int observedBitDepth = pixelType.getBitsPerPixel()
        String observedRepresentation
        if (pixelType.isUnsignedInteger()) {
            observedRepresentation = "unsigned_integer"
        } else if (pixelType.isFloatingPoint()) {
            observedRepresentation = "floating_point"
        } else {
            fail(
                "current image uses signed integer pixels, which the v1 pilot " +
                "intensity descriptor does not support"
            )
        }
        for (Map<String, Object> channel : channels) {
            int index = (channel.get("source_channel_index") as Number).intValue()
            if (index < 0 || index >= serverChannels.size()) fail("configured source channel index is outside image range")
            String observedChannelName = serverChannels.get(index).getName()
            if (observedChannelName != channel.get("source_channel_name")) {
                fail("current image channel " + index + " does not match configured source channel name")
            }
            Map<String, Object> intensity = requireMap(
                channel.get("intensity"),
                "channel intensity"
            )
            if ((intensity.get("bit_depth") as Number).intValue() !=
                observedBitDepth ||
                intensity.get("representation") != observedRepresentation) {
                fail(
                    "configured channel " + index +
                    " bit depth/representation does not match server pixel type " +
                    pixelType.toString()
                )
            }
        }

        Map<String, Object> expectedCalibration = requireMap(imageConfig.get("calibration"), "image.calibration")
        def observedCalibration = server.getPixelCalibration()
        if (!observedCalibration.hasPixelSizeMicrons()) fail("current image lacks pixel calibration in microns")
        double width = finiteDouble(observedCalibration.getPixelWidthMicrons(), "observed pixel width")
        double height = finiteDouble(observedCalibration.getPixelHeightMicrons(), "observed pixel height")
        double expectedWidth = (expectedCalibration.get("expected_pixel_width_um") as Number).doubleValue()
        double expectedHeight = (expectedCalibration.get("expected_pixel_height_um") as Number).doubleValue()
        double tolerance = (expectedCalibration.get("tolerance_um") as Number).doubleValue()
        if (Math.abs(width - expectedWidth) > tolerance || Math.abs(height - expectedHeight) > tolerance) {
            fail("observed pixel calibration differs from config")
        }
        Object zSpacing = null
        if (observedCalibration.hasZSpacingMicrons()) {
            zSpacing = finiteDouble(observedCalibration.getZSpacingMicrons(), "observed z spacing")
            if ((zSpacing as double) <= 0.0d) fail("observed z spacing must be positive")
        }
        Map<String, Object> pixelCalibration = [
            calibration_id: expectedCalibration.get("calibration_id"),
            pixel_width_um: width,
            pixel_height_um: height,
            z_spacing_um: zSpacing,
            unit: "um"
        ]
        Map<String, Object> coordinateSpace = [
            coordinate_space_id: imageConfig.get("coordinate_space_id"),
            dimension: "2d",
            geometry_unit: "pixel",
            axis_order: ["x", "y"],
            origin: "top_left",
            x_axis_direction: "right",
            y_axis_direction: "down"
        ]
        return [
            dimensions: [
                width_pixels: widthPixels,
                height_pixels: heightPixels,
                z_planes: 1,
                timepoints: 1
            ],
            pixel_calibration: pixelCalibration,
            coordinate_space: coordinateSpace
        ]
    }

    static Map<String, Object> buildImageManifest(
        Map<String, Object> config,
        Map<String, Object> runtime,
        String scriptSha256,
        String configSha256
    ) {
        Map<String, Object> provenance = requireMap(config.get("provenance"), "image.provenance")
        return [
            "\$schema": IMAGE_SCHEMA,
            contract_type: "ifquant_platform_image_manifest",
            contract_version: CONTRACT_VERSION,
            image_id: config.get("image_id"),
            biological_unit_id: config.get("biological_unit_id"),
            source_artifact: config.get("source_artifact"),
            dimensions: runtime.get("dimensions"),
            pixel_calibration: runtime.get("pixel_calibration"),
            coordinate_space: runtime.get("coordinate_space"),
            acquisition: config.get("acquisition"),
            provenance: [
                created_at: provenance.get("created_at"),
                producer_id: provenance.get("producer_id"),
                producer_version: provenance.get("producer_version"),
                code_sha256: scriptSha256,
                ingest_config_sha256: configSha256
            ]
        ]
    }

    static Map<String, Object> buildChannelManifest(
        Map<String, Object> config,
        String imageId,
        String scriptSha256
    ) {
        Map<String, Object> provenance = requireMap(config.get("provenance"), "channel_map.provenance")
        List<Map<String, Object>> channels = typedMapList(requireList(config.get("channels"), "channel_map.channels"), "channel_map.channels")
        return [
            "\$schema": CHANNEL_SCHEMA,
            contract_type: "ifquant_platform_channel_map",
            contract_version: CONTRACT_VERSION,
            channel_map_id: config.get("channel_map_id"),
            image_id: imageId,
            channels: channels,
            provenance: [
                created_at: provenance.get("created_at"),
                producer_id: provenance.get("producer_id"),
                producer_version: provenance.get("producer_version"),
                code_sha256: scriptSha256,
                mapping_config_sha256: canonicalSha256(channels)
            ]
        ]
    }

    static Map<Object, Map<String, Object>> buildAnnotationRecords(
        List annotations,
        String imageId,
        String annotationSetId,
        String classification
    ) {
        Map<Object, Map<String, Object>> result = new IdentityHashMap<>()
        Set<String> ids = new HashSet<>()
        for (def annotation : annotations) {
            def roi = annotation.getROI()
            if (roi == null) fail("selected annotation has no ROI")
            Geometry geometry = normalizedGeometry(roi.getGeometry(), "annotation geometry")
            Map<String, Object> geometryRecord = wktRecord(geometry)
            String annotationId = "ann_" + canonicalSha256([
                annotation_set_id: annotationSetId,
                image_id: imageId,
                label: classification,
                wkt: geometryRecord.get("wkt")
            ])
            if (!ids.add(annotationId)) fail("duplicate normalized annotation identity")
            result.put(annotation, [
                annotation_id: annotationId,
                label: classification,
                inclusion_policy: "include",
                geometry: geometryRecord,
                review: [state: "unreviewed", reviewer_id: null, reviewed_at: null]
            ])
        }
        return result
    }

    static Map<String, Object> buildAnnotationManifest(
        Map<String, Object> config,
        String imageId,
        String coordinateSpaceId,
        List<Map<String, Object>> annotations,
        String scriptSha256
    ) {
        annotations.sort { left, right ->
            left.get("annotation_id").toString() <=> right.get("annotation_id").toString()
        }
        Map<String, Object> provenance = requireMap(config.get("provenance"), "annotation_set.provenance")
        return [
            "\$schema": ANNOTATION_SCHEMA,
            contract_type: "ifquant_platform_annotation_set",
            contract_version: CONTRACT_VERSION,
            annotation_set_id: config.get("annotation_set_id"),
            image_id: imageId,
            coordinate_space_id: coordinateSpaceId,
            revision: config.get("revision"),
            annotations: annotations,
            provenance: [
                created_at: provenance.get("created_at"),
                source_system: provenance.get("source_system"),
                producer_id: provenance.get("producer_id"),
                producer_version: provenance.get("producer_version"),
                code_sha256: scriptSha256,
                parent_annotation_set_id: provenance.get("parent_annotation_set_id")
            ]
        ]
    }

    static String annotationContentSha256(
        Map<String, Object> config,
        String imageId,
        String coordinateSpaceId,
        List<Map<String, Object>> records
    ) {
        List<Map<String, Object>> content = records.collect { record ->
            [
                annotation_id: record.get("annotation_id"),
                label: record.get("label"),
                inclusion_policy: record.get("inclusion_policy"),
                geometry: record.get("geometry")
            ]
        }
        content.sort { left, right ->
            left.get("annotation_id").toString() <=>
                right.get("annotation_id").toString()
        }
        return canonicalSha256([
            contract: "ifquant-platform-annotation-content/v1",
            annotation_set_id: config.get("annotation_set_id"),
            image_id: imageId,
            coordinate_space_id: coordinateSpaceId,
            revision: config.get("revision"),
            annotations: content
        ])
    }

    static Map<String, Object> buildSegmentationManifest(
        Map<String, Object> config,
        String imageId,
        String channelMapId,
        String annotationSetId,
        String coordinateSpaceId,
        String scriptSha256,
        String configSha256,
        int exportedCellCount,
        Map<String, Integer> exclusionCounts,
        Instant pluginStartedAt,
        Instant pluginCompletedAt
    ) {
        Map<String, Object> detector = requireMap(config.get("detector"), "segmentation.detector")
        Map<String, Object> provenance = requireMap(config.get("provenance"), "segmentation.provenance")
        Map<String, Object> configuredQc = requireMap(config.get("qc"), "segmentation.qc")
        List<Map<String, Object>> flags = typedMapList(
            requireList(configuredQc.get("flags"), "segmentation.qc.flags"),
            "segmentation.qc.flags"
        ).collect { new LinkedHashMap<>(it) }
        appendExclusionQcFlags(flags, exclusionCounts)
        String qcStatus = configuredQc.get("status").toString()
        if (exportedCellCount == 0) {
            qcStatus = "not_evaluated"
            appendExporterQcFlag(flags, [
                code: "zero_cells_exported",
                severity: "warning",
                message: "Detection produced no exportable cells; scientific QC remains not evaluated."
            ])
        }
        flags.sort { left, right ->
            left.get("code").toString() <=> right.get("code").toString()
        }
        return [
            "\$schema": SEGMENTATION_SCHEMA,
            contract_type: "ifquant_platform_segmentation_run",
            contract_version: CONTRACT_VERSION,
            segmentation_run_id: config.get("segmentation_run_id"),
            image_id: imageId,
            channel_map_id: channelMapId,
            annotation_set_id: annotationSetId,
            coordinate_space_id: coordinateSpaceId,
            backend: config.get("backend"),
            detector: [
                detector_id: detector.get("detector_id"),
                detector_version: detector.get("detector_version"),
                config_sha256: canonicalSha256(config.get("parameters"))
            ],
            model: config.get("model"),
            preprocessing: config.get("preprocessing"),
            boundary_policy: config.get("boundary_policy"),
            execution: [
                script_sha256: scriptSha256,
                run_config_sha256: configSha256,
                started_at: pluginStartedAt.toString(),
                completed_at: pluginCompletedAt.toString()
            ],
            qc: [status: qcStatus, flags: flags],
            provenance: [
                created_at: provenance.get("created_at"),
                producer_id: provenance.get("producer_id"),
                producer_version: provenance.get("producer_version"),
                code_revision: provenance.get("code_revision"),
                runtime_sha256: provenance.get("runtime_sha256")
            ]
        ]
    }

    static Map<String, Object> buildCellDraft(
        def cell,
        Map<String, Object> annotation,
        String packageId,
        String imageId,
        String biologicalUnitId,
        String segmentationRunId,
        String coordinateSpaceId,
        Map<String, Object> calibration,
        Map<String, Object> mappings,
        Map<String, Object> qcConfig,
        Map<String, Object> provenanceConfig,
        String scriptSha256
    ) {
        def cellRoi = cell.getROI()
        def nucleusRoi = cell.getNucleusROI()
        if (cellRoi == null || nucleusRoi == null) fail("every exported cell requires cell and nucleus ROIs")
        Geometry cellGeometry = normalizedGeometry(cellRoi.getGeometry(), "cell geometry")
        Geometry nucleusGeometry = normalizedGeometry(nucleusRoi.getGeometry(), "nucleus geometry")
        Map<String, Object> cellWkt = wktRecord(cellGeometry)
        Map<String, Object> nucleusWkt = wktRecord(nucleusGeometry)
        double cellX = finiteDouble(cellGeometry.getCentroid().getX(), "cell centroid x")
        double cellY = finiteDouble(cellGeometry.getCentroid().getY(), "cell centroid y")
        double nucleusX = finiteDouble(nucleusGeometry.getCentroid().getX(), "nucleus centroid x")
        double nucleusY = finiteDouble(nucleusGeometry.getCentroid().getY(), "nucleus centroid y")
        String annotationId = annotation.get("annotation_id").toString()
        def detectionUuid = cell.getID()
        if (detectionUuid == null) fail("exportable cell lacks a QuPath detection UUID")
        String sourceDetectionId = requireIdentifier(
            detectionUuid.toString(),
            "QuPath detection UUID"
        )
        String objectId = canonicalSha256([
            annotation_id: annotationId,
            cell_wkt: cellWkt.get("wkt"),
            image_id: imageId,
            nucleus_wkt: nucleusWkt.get("wkt"),
            segmentation_run_id: segmentationRunId
        ])

        double pixelWidth = (calibration.get("pixel_width_um") as Number).doubleValue()
        double pixelHeight = (calibration.get("pixel_height_um") as Number).doubleValue()
        Geometry calibratedCell = scaleGeometry(cellGeometry, pixelWidth, pixelHeight)
        Geometry calibratedNucleus = scaleGeometry(nucleusGeometry, pixelWidth, pixelHeight)
        Map<String, Double> morphologyValues = morphologyValues(calibratedCell, calibratedNucleus)
        List<Map<String, Object>> morphology = []
        for (Map<String, Object> mapping : typedMapList(requireList(mappings.get("morphology"), "morphology mappings"), "morphology mappings")) {
            String key = mapping.get("compartment").toString() + ":" + mapping.get("feature").toString()
            Double value = morphologyValues.get(key)
            if (value == null) fail("unsupported morphology mapping " + key)
            morphology.add([
                measurement_id: mapping.get("measurement_id"),
                compartment: mapping.get("compartment"),
                feature: mapping.get("feature"),
                value: value,
                unit: mapping.get("unit")
            ])
        }
        morphology.sort { left, right ->
            left.get("measurement_id").toString() <=> right.get("measurement_id").toString()
        }

        List<Map<String, Object>> intensity = []
        def measurementList = cell.getMeasurementList()
        for (Map<String, Object> mapping : typedMapList(requireList(mappings.get("intensity"), "intensity mappings"), "intensity mappings")) {
            String sourceName = mapping.get("source_measurement").toString()
            if (!measurementList.containsKey(sourceName)) {
                fail("cell " + objectId + " lacks exact source measurement " + quoted(sourceName))
            }
            intensity.add([
                measurement_id: mapping.get("measurement_id"),
                channel_id: mapping.get("channel_id"),
                marker_id: mapping.get("marker_id"),
                compartment: mapping.get("compartment"),
                statistic: mapping.get("statistic"),
                value: finiteDouble(measurementList.get(sourceName), "measurement " + sourceName),
                unit: mapping.get("unit")
            ])
        }
        intensity.sort { left, right ->
            left.get("measurement_id").toString() <=> right.get("measurement_id").toString()
        }

        List<Map<String, Object>> qcFlags = typedMapList(
            requireList(qcConfig.get("object_default_flags"), "qc.object_default_flags"),
            "qc.object_default_flags"
        ).collect { new LinkedHashMap<>(it) }
        if (!cellGeometry.covers(nucleusGeometry)) {
            appendExporterQcFlag(qcFlags, [
                code: "nucleus_not_covered_by_cell_geometry",
                severity: "warning",
                message: "Normalized nucleus geometry is not covered by cell geometry."
            ])
        }
        qcFlags.sort { left, right ->
            left.get("code").toString() <=> right.get("code").toString()
        }

        Map<String, Object> record = [
            "\$schema": CELL_SCHEMA,
            contract_type: "ifquant_platform_cell_object",
            contract_version: CONTRACT_VERSION,
            object_id: objectId,
            object_index: null,
            package_id: packageId,
            image_id: imageId,
            biological_unit_id: biologicalUnitId,
            annotation_id: annotationId,
            segmentation_run_id: segmentationRunId,
            coordinate_space_id: coordinateSpaceId,
            geometry: [cell: cellWkt, nucleus: nucleusWkt],
            centroids: [
                cell_x: cellX,
                cell_y: cellY,
                nucleus_x: nucleusX,
                nucleus_y: nucleusY,
                unit: "pixel"
            ],
            morphology_measurements: morphology,
            intensity_measurements: intensity,
            qc: [status: qcConfig.get("object_default_status"), flags: qcFlags],
            review: [
                state: "unreviewed",
                revision: 0,
                reviewer_id: null,
                reviewed_at: null,
                notes: null,
                supersedes_object_id: null
            ],
            provenance: [
                created_at: provenanceConfig.get("created_at"),
                source_detection_id: sourceDetectionId,
                exporter_id: provenanceConfig.get("exporter_id"),
                exporter_version: provenanceConfig.get("exporter_version"),
                exporter_code_sha256: scriptSha256
            ]
        ]
        return [
            cell: cell,
            annotation_id: annotationId,
            cell_y: cellY,
            cell_x: cellX,
            cell_wkt: cellWkt.get("wkt"),
            record: record
        ]
    }

    static Map<String, Object> buildCandidateDispositionLedger(
        List<Map<String, Object>> assignments,
        Map<Object, Map<String, Object>> annotationByObject,
        Map<Object, String> acceptedObjectIdByCell,
        String packageId,
        String imageId,
        String annotationSetId,
        String segmentationRunId,
        String coordinateSpaceId
    ) {
        List<Map<String, Object>> drafts = []
        for (Map<String, Object> assignment : assignments) {
            def cell = assignment.get("cell")
            if (cell == null) fail("candidate assignment lacks a cell object")
            Geometry cellGeometry = (Geometry) assignment.get("cell_geometry")
            if (cellGeometry == null) {
                fail("candidate assignment lacks normalized cell geometry")
            }
            Geometry nucleusGeometry =
                (Geometry) assignment.get("nucleus_geometry")
            Map<String, Object> cellWkt = wktRecord(cellGeometry)
            Map<String, Object> nucleusWkt = nucleusGeometry == null ? null :
                wktRecord(nucleusGeometry)
            double cellX = finiteDouble(
                cellGeometry.getCentroid().getX(),
                "candidate cell centroid x"
            )
            double cellY = finiteDouble(
                cellGeometry.getCentroid().getY(),
                "candidate cell centroid y"
            )
            Double nucleusX = nucleusGeometry == null ? null : finiteDouble(
                nucleusGeometry.getCentroid().getX(),
                "candidate nucleus centroid x"
            )
            Double nucleusY = nucleusGeometry == null ? null : finiteDouble(
                nucleusGeometry.getCentroid().getY(),
                "candidate nucleus centroid y"
            )
            Double nucleusAreaOutsideCell = null
            Double nucleusAreaOutsideCellFraction = null
            if (nucleusGeometry != null) {
                double nucleusArea = positiveGeometryValue(
                    nucleusGeometry.getArea(),
                    "candidate nucleus area"
                )
                nucleusAreaOutsideCell = finiteDouble(
                    nucleusGeometry.difference(cellGeometry).getArea(),
                    "candidate nucleus area outside cell"
                )
                nucleusAreaOutsideCellFraction = boundedRatio(
                    nucleusAreaOutsideCell / nucleusArea,
                    "candidate nucleus area outside cell fraction"
                )
            }

            def annotationObject = assignment.get("annotation")
            String annotationId = null
            if (annotationObject != null) {
                Map<String, Object> annotation =
                    annotationByObject.get(annotationObject)
                if (annotation == null) {
                    fail("candidate's unambiguous annotation lacks a canonical record")
                }
                annotationId = annotation.get("annotation_id").toString()
            }

            boolean accepted = assignment.get("include") == Boolean.TRUE
            String acceptedObjectId = acceptedObjectIdByCell.get(cell)
            if (accepted && acceptedObjectId == null) {
                fail("accepted candidate lacks its canonical object_id")
            }
            if (!accepted && acceptedObjectId != null) {
                fail("excluded candidate unexpectedly maps to a canonical object_id")
            }
            String reason = accepted ? "accepted" :
                assignment.get("exclusion_reason")?.toString()
            if (reason == null || reason.isEmpty()) {
                fail("candidate disposition lacks a reason")
            }

            def detectionUuid = cell.getID()
            if (detectionUuid == null) {
                fail("candidate cell lacks a QuPath detection UUID")
            }
            String sourceDetectionId = requireIdentifier(
                detectionUuid.toString(),
                "QuPath candidate detection UUID"
            )
            String candidateId = "cand_" + canonicalSha256([
                cell_wkt: cellWkt.get("wkt"),
                coordinate_space_id: coordinateSpaceId,
                image_id: imageId,
                nucleus_wkt: nucleusWkt == null ? null : nucleusWkt.get("wkt"),
                segmentation_run_id: segmentationRunId
            ])
            boolean nucleusNotCoveredByCell = assignment.get(
                "nucleus_not_covered_by_cell_geometry_warning"
            ) == Boolean.TRUE
            Map<String, Object> record = [
                schema_version: CANDIDATE_DISPOSITION_SCHEMA,
                candidate_id: candidateId,
                candidate_index: null,
                package_id: packageId,
                image_id: imageId,
                annotation_set_id: annotationSetId,
                segmentation_run_id: segmentationRunId,
                coordinate_space_id: coordinateSpaceId,
                annotation_id: annotationId,
                accepted_object_id: acceptedObjectId,
                source_detection_id: sourceDetectionId,
                disposition: accepted ? "accepted" : "excluded",
                reason: reason,
                geometry: [cell: cellWkt, nucleus: nucleusWkt],
                centroids: [
                    cell_x: cellX,
                    cell_y: cellY,
                    nucleus_x: nucleusX,
                    nucleus_y: nucleusY,
                    unit: "pixel"
                ],
                touches_annotation_boundary:
                    assignment.get("touches_boundary") == Boolean.TRUE,
                nucleus_not_covered_by_cell_geometry_warning:
                    nucleusNotCoveredByCell,
                nucleus_area_outside_cell_px2: nucleusAreaOutsideCell,
                nucleus_area_outside_cell_fraction:
                    nucleusAreaOutsideCellFraction
            ]
            drafts.add([
                candidate_id: candidateId,
                cell_x: cellX,
                cell_y: cellY,
                cell_wkt: cellWkt.get("wkt"),
                nucleus_wkt: nucleusWkt == null ? null : nucleusWkt.get("wkt"),
                record: record
            ])
        }

        drafts.sort { left, right ->
            int comparison = (
                (left.get("cell_y") as Number).doubleValue() <=>
                (right.get("cell_y") as Number).doubleValue()
            )
            if (comparison != 0) return comparison
            comparison = (
                (left.get("cell_x") as Number).doubleValue() <=>
                (right.get("cell_x") as Number).doubleValue()
            )
            if (comparison != 0) return comparison
            comparison = left.get("cell_wkt").toString() <=>
                right.get("cell_wkt").toString()
            if (comparison != 0) return comparison
            comparison = (left.get("nucleus_wkt") ?: "").toString() <=>
                (right.get("nucleus_wkt") ?: "").toString()
            if (comparison != 0) return comparison
            return left.get("candidate_id").toString() <=>
                right.get("candidate_id").toString()
        }

        List<Map<String, Object>> records = []
        Set<String> candidateIds = new HashSet<>()
        Map<String, Integer> dispositionCounts = new TreeMap<>()
        Map<String, Integer> reasonCounts = new TreeMap<>()
        int uncoveredNucleusCount = 0
        for (int index = 0; index < drafts.size(); index++) {
            Map<String, Object> record =
                (Map<String, Object>) drafts.get(index).get("record")
            record.put("candidate_index", index)
            String candidateId = record.get("candidate_id").toString()
            if (!candidateIds.add(candidateId)) {
                fail("duplicate deterministic candidate_id " + candidateId)
            }
            String disposition = record.get("disposition").toString()
            String reason = record.get("reason").toString()
            dispositionCounts.put(
                disposition,
                (dispositionCounts.get(disposition) ?: 0) + 1
            )
            reasonCounts.put(reason, (reasonCounts.get(reason) ?: 0) + 1)
            if (record.get(
                "nucleus_not_covered_by_cell_geometry_warning"
            ) == Boolean.TRUE) {
                uncoveredNucleusCount++
            }
            records.add(record)
        }
        for (String disposition : ["accepted", "excluded"]) {
            if (!dispositionCounts.containsKey(disposition)) {
                dispositionCounts.put(disposition, 0)
            }
        }
        int acceptedCount = dispositionCounts.get("accepted") ?: 0
        if (acceptedCount != acceptedObjectIdByCell.size()) {
            fail("candidate disposition accepted count does not match cell objects")
        }
        if ((dispositionCounts.get("accepted") +
            dispositionCounts.get("excluded")) != records.size()) {
            fail("candidate disposition counts do not reconcile to records")
        }
        return [
            records: records,
            disposition_counts: dispositionCounts,
            reason_counts: reasonCounts,
            geometry_warning_counts: [
                nucleus_not_covered_by_cell_geometry: uncoveredNucleusCount
            ]
        ]
    }

    static Map<String, Object> buildCandidateDispositionManifest(
        String packageId,
        String imageId,
        String annotationSetId,
        String segmentationRunId,
        String coordinateSpaceId,
        int recordCount,
        long sizeBytes,
        String artifactSha256,
        Map<String, Integer> dispositionCounts,
        Map<String, Integer> reasonCounts,
        Map<String, Integer> geometryWarningCounts,
        String scriptSha256,
        String configSha256,
        String sourceArtifactSha256,
        String annotationContentSha256
    ) {
        return [
            schema_version: CANDIDATE_DISPOSITIONS_MANIFEST_SCHEMA,
            pilot_status: PILOT_STATUS,
            package_id: packageId,
            image_id: imageId,
            annotation_set_id: annotationSetId,
            segmentation_run_id: segmentationRunId,
            coordinate_space_id: coordinateSpaceId,
            artifact: [
                relative_path: CANDIDATE_DISPOSITIONS_PATH,
                media_type: "application/x-ndjson",
                sha256: artifactSha256,
                size_bytes: sizeBytes,
                record_count: recordCount,
                ordering: "candidate_index_ascending"
            ],
            disposition_counts: dispositionCounts,
            reason_counts: reasonCounts,
            geometry_warning_counts: geometryWarningCounts,
            bindings: [
                script_sha256: scriptSha256,
                run_config_sha256: configSha256,
                source_artifact_sha256: sourceArtifactSha256,
                annotation_content_sha256: annotationContentSha256
            ],
            claims: [
                scientific_validation: false,
                backend_equivalence: false,
                model_universality: false,
                authorization: "none"
            ]
        ]
    }

    static Map<String, Double> morphologyValues(Geometry cell, Geometry nucleus) {
        double cellArea = positiveGeometryValue(cell.getArea(), "cell area")
        double cellPerimeter = positiveGeometryValue(cell.getLength(), "cell perimeter")
        double nucleusArea = positiveGeometryValue(nucleus.getArea(), "nucleus area")
        double nucleusPerimeter = positiveGeometryValue(nucleus.getLength(), "nucleus perimeter")
        double cellCircularity = boundedRatio(4.0d * Math.PI * cellArea / (cellPerimeter * cellPerimeter), "cell circularity")
        double nucleusCircularity = boundedRatio(4.0d * Math.PI * nucleusArea / (nucleusPerimeter * nucleusPerimeter), "nucleus circularity")
        double areaRatio = boundedRatio(nucleusArea / cellArea, "nucleus to cell area ratio")
        return [
            "cell:area": cellArea,
            "cell:perimeter": cellPerimeter,
            "cell:circularity": cellCircularity,
            "nucleus:area": nucleusArea,
            "nucleus:perimeter": nucleusPerimeter,
            "nucleus:circularity": nucleusCircularity,
            "nucleus:nucleus_cell_area_ratio": areaRatio
        ]
    }

    static Map<String, Object> buildPackage(
        Map<String, Object> packageConfig,
        Map<String, Object> image,
        Map<String, Object> channelMap,
        Map<String, Object> annotationSet,
        Map<String, Object> segmentationRun,
        Map<String, Object> method,
        Map<String, Object> calibration,
        Map<String, Object> coordinateSpace,
        int objectCount,
        long sizeBytes,
        String cellsSha256,
        Map<String, Object> qcConfig,
        Map<String, Object> provenanceConfig,
        String configSha256,
        Map<String, Integer> objectQcFlagCounts,
        Map<String, Integer> exclusionCounts
    ) {
        Map<String, Object> acquisition = requireMap(image.get("acquisition"), "image.acquisition")
        Map<String, Object> backend = requireMap(segmentationRun.get("backend"), "segmentation_run.backend")
        Map<String, Object> detector = requireMap(segmentationRun.get("detector"), "segmentation_run.detector")
        Map<String, Object> model = requireMap(segmentationRun.get("model"), "segmentation_run.model")
        Map<String, Object> preprocessing = requireMap(segmentationRun.get("preprocessing"), "segmentation_run.preprocessing")
        List<Map<String, Object>> packageFlags = typedMapList(
            requireList(qcConfig.get("package_flags"), "qc.package_flags"),
            "qc.package_flags"
        ).collect { new LinkedHashMap<>(it) }
        appendExclusionQcFlags(packageFlags, exclusionCounts)
        Integer uncoveredNucleusCount = objectQcFlagCounts.get(
            "nucleus_not_covered_by_cell_geometry"
        )
        if (uncoveredNucleusCount != null && uncoveredNucleusCount > 0) {
            appendExporterQcFlag(packageFlags, [
                code: "objects_nucleus_not_covered_by_cell_geometry",
                severity: "warning",
                message: uncoveredNucleusCount +
                    " exported object(s) have normalized nucleus geometry " +
                    "that is not covered by cell geometry."
            ])
        }
        if (objectCount == 0) {
            appendExporterQcFlag(packageFlags, [
                code: "zero_cells_exported",
                severity: "warning",
                message: "The package contains zero cells; scientific QC remains not evaluated."
            ])
        }
        packageFlags.sort { left, right ->
            left.get("code").toString() <=> right.get("code").toString()
        }
        return [
            "\$schema": PACKAGE_SCHEMA,
            contract_type: "ifquant_platform_cell_object_package",
            contract_version: CONTRACT_VERSION,
            package_id: packageConfig.get("package_id"),
            image: [
                image_id: image.get("image_id"),
                manifest_relative_path: IMAGE_MANIFEST_PATH,
                manifest_sha256: canonicalSha256(image),
                source_sha256: requireMap(image.get("source_artifact"), "source_artifact").get("sha256")
            ],
            biological_unit: [
                biological_unit_id: image.get("biological_unit_id"),
                mouse_id: acquisition.get("mouse_id"),
                specimen_id: acquisition.get("specimen_id"),
                section_id: acquisition.get("section_id"),
                slide_id: acquisition.get("slide_id"),
                batch_id: acquisition.get("batch_id"),
                scanner_id: acquisition.get("scanner_id")
            ],
            channel_map: [
                channel_map_id: channelMap.get("channel_map_id"),
                manifest_relative_path: CHANNEL_MANIFEST_PATH,
                manifest_sha256: canonicalSha256(channelMap)
            ],
            annotation_set: [
                annotation_set_id: annotationSet.get("annotation_set_id"),
                manifest_relative_path: ANNOTATION_MANIFEST_PATH,
                manifest_sha256: canonicalSha256(annotationSet)
            ],
            pixel_calibration: calibration,
            coordinate_space: coordinateSpace,
            segmentation_run: [
                segmentation_run_id: segmentationRun.get("segmentation_run_id"),
                manifest_relative_path: SEGMENTATION_MANIFEST_PATH,
                manifest_sha256: canonicalSha256(segmentationRun),
                backend_kind: backend.get("kind"),
                backend_sha256: backend.get("artifact_sha256"),
                model_sha256: model.get("descriptor_sha256"),
                weights_sha256: model.get("weights_sha256"),
                detector_config_sha256: detector.get("config_sha256"),
                preprocessing_sha256: preprocessing.get("profile_sha256")
            ],
            measurement_method: [
                definition_id: method.get("definition_id"),
                definition_relative_path: method.get("definition_relative_path"),
                definition_sha256: method.get("definition_sha256"),
                parameter_set_id: method.get("parameter_set_id"),
                parameter_set_relative_path: method.get("parameter_set_relative_path"),
                parameter_set_sha256: method.get("parameter_set_sha256"),
                method_instance_sha256: method.get("method_instance_sha256")
            ],
            cell_objects_artifact: [
                relative_path: CELL_OBJECTS_PATH,
                media_type: "application/x-ndjson",
                schema_id: CELL_SCHEMA,
                sha256: cellsSha256,
                size_bytes: sizeBytes,
                record_count: objectCount,
                ordering: "object_index_ascending"
            ],
            qc: [
                status: "not_evaluated",
                object_count: objectCount,
                pass_count: 0,
                warning_count: 0,
                fail_count: 0,
                not_evaluated_count: objectCount,
                flags: packageFlags
            ],
            review: [
                state: "unreviewed",
                reviewed_object_count: 0,
                reviewer_ids: [],
                last_reviewed_at: null
            ],
            provenance: [
                created_at: provenanceConfig.get("created_at"),
                producer_id: provenanceConfig.get("exporter_id"),
                producer_version: provenanceConfig.get("exporter_version"),
                code_revision: provenanceConfig.get("code_revision"),
                package_config_sha256: configSha256,
                parent_package_id: packageConfig.get("parent_package_id")
            ]
        ]
    }

    static Object parseStrictJson(byte[] bytes) {
        String text = decodeStrictUtf8(bytes, "JSON input")
        JsonReader reader = new JsonReader(new StringReader(text))
        reader.setLenient(false)
        try {
            Object value = parseJsonValue(reader, "\$")
            if (reader.peek() != JsonToken.END_DOCUMENT) fail("JSON has trailing content")
            return value
        } catch (IllegalStateException error) {
            if (error.message != null && error.message.startsWith("IFQUANT_PILOT_ERROR:")) throw error
            fail("invalid JSON: " + error.message)
            return null
        } catch (Exception error) {
            fail("invalid JSON: " + error.message)
            return null
        } finally {
            reader.close()
        }
    }

    static Object parseJsonValue(JsonReader reader, String context) {
        switch (reader.peek()) {
            case JsonToken.BEGIN_OBJECT:
                reader.beginObject()
                Map<String, Object> object = new LinkedHashMap<>()
                Set<String> keys = new HashSet<>()
                while (reader.hasNext()) {
                    String key = reader.nextName()
                    if (!keys.add(key)) fail("duplicate JSON key at " + context + "." + key)
                    object.put(key, parseJsonValue(reader, context + "." + key))
                }
                reader.endObject()
                return object
            case JsonToken.BEGIN_ARRAY:
                reader.beginArray()
                List<Object> array = []
                int index = 0
                while (reader.hasNext()) {
                    array.add(parseJsonValue(reader, context + "[" + index + "]"))
                    index++
                }
                reader.endArray()
                return array
            case JsonToken.STRING:
                return reader.nextString()
            case JsonToken.NUMBER:
                return parseJsonNumber(reader.nextString(), context)
            case JsonToken.BOOLEAN:
                return reader.nextBoolean()
            case JsonToken.NULL:
                reader.nextNull()
                return null
            default:
                fail("unexpected JSON token at " + context)
                return null
        }
    }

    static String decodeStrictUtf8(byte[] bytes, String context) {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString()
        } catch (Exception error) {
            fail(context + " is not strict UTF-8: " + error.message)
            return null
        }
    }

    static int countOccurrences(String text, String needle) {
        int count = 0
        int offset = 0
        while (true) {
            int next = text.indexOf(needle, offset)
            if (next < 0) return count
            count++
            offset = next + needle.length()
        }
    }

    static Number parseJsonNumber(String lexical, String context) {
        if (!JSON_NUMBER.matcher(lexical).matches()) fail("invalid JSON number at " + context)
        BigDecimal decimal
        try {
            decimal = new BigDecimal(lexical)
        } catch (NumberFormatException error) {
            fail("invalid JSON number at " + context)
            return null
        }
        if (decimal.signum() == 0 && lexical.startsWith("-")) fail("negative zero is not permitted at " + context)
        double binary64 = decimal.doubleValue()
        if (!Double.isFinite(binary64)) fail("number exceeds binary64 range at " + context)
        if (decimal.signum() != 0 && binary64 == 0.0d) fail("number underflows binary64 at " + context)
        if (Math.abs(binary64) > MAX_SAFE_INTEGER.doubleValue()) fail("number exceeds interoperable safe range at " + context)
        if (!lexical.contains(".") && !lexical.contains("e") && !lexical.contains("E")) {
            BigInteger integer = decimal.toBigIntegerExact()
            return integer.bitLength() < 31 ? integer.intValue() : integer.longValue()
        }
        if (binary64 == Math.rint(binary64)) return BigDecimal.valueOf(binary64).toBigIntegerExact()
        return BigDecimal.valueOf(binary64)
    }

    static Map<String, Object> loadStrictObject(Path path, String context) {
        if (!Files.isRegularFile(path) || !Files.isReadable(path)) {
            fail(context + " is not a readable regular file: " + path)
        }
        return requireMap(parseStrictJson(Files.readAllBytes(path)), context)
    }

    static void publishJson(
        Path root,
        String relative,
        Map<String, Object> document,
        List<Path> published
    ) {
        Path path = packageRelativePath(root, relative)
        ensureParentDirectory(path)
        writeJsonAtomic(path, document)
        published.add(path)
    }

    static String writeJsonLinesAtomic(Path finalPath, List<Map<String, Object>> records) {
        Path temporary = siblingTemporary(finalPath)
        MessageDigest digest = MessageDigest.getInstance("SHA-256")
        try {
            def raw = Files.newOutputStream(temporary, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
            def digestStream = new DigestOutputStream(raw, digest)
            def writer = new BufferedWriter(new OutputStreamWriter(digestStream, StandardCharsets.UTF_8))
            try {
                for (Map<String, Object> record : records) {
                    writer.write(canonicalJson(record))
                    writer.write("\n")
                }
            } finally {
                writer.close()
            }
            moveAtomic(temporary, finalPath)
            return hex(digest.digest())
        } catch (Throwable failure) {
            Files.deleteIfExists(temporary)
            throw failure
        }
    }

    static void writeJsonAtomic(Path finalPath, Map<String, Object> document) {
        Path temporary = siblingTemporary(finalPath)
        try {
            Files.write(
                temporary,
                (canonicalJson(document) + "\n").getBytes(StandardCharsets.UTF_8),
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE
            )
            moveAtomic(temporary, finalPath)
        } catch (Throwable failure) {
            Files.deleteIfExists(temporary)
            throw failure
        }
    }

    static void moveAtomic(Path source, Path target) {
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE)
        } catch (AtomicMoveNotSupportedException error) {
            fail("filesystem lacks atomic move support for " + target)
        }
    }

    static Path siblingTemporary(Path finalPath) {
        return finalPath.resolveSibling(
            "." + finalPath.getFileName().toString() + "." + UUID.randomUUID().toString() + ".tmp"
        )
    }

    static void prepareEmptyOutputDirectory(Path outputDirectory) {
        if (outputDirectory.getParent() == null) fail("output_directory must not be a filesystem root")
        if (Files.exists(outputDirectory)) {
            if (!Files.isDirectory(outputDirectory)) fail("output_directory exists and is not a directory")
            def entries = Files.list(outputDirectory)
            try {
                if (entries.findAny().isPresent()) fail("output_directory must be empty; refusing overwrite")
            } finally {
                entries.close()
            }
        } else {
            Files.createDirectories(outputDirectory)
        }
    }

    static Path resolveInputPath(Path configPath, String configured) {
        Path path = Paths.get(configured)
        if (!path.isAbsolute()) path = configPath.getParent().resolve(path)
        return path.toAbsolutePath().normalize()
    }

    static Path requireExecutingScriptPath(Object value) {
        if (value == null) {
            fail(
                "QuPath ScriptAttributes.FILE_PATH is unavailable; this CLI " +
                "pilot requires QuPath to expose the executing script path"
            )
        }
        Path path
        try {
            if (value instanceof Path) {
                path = (Path) value
            } else if (value instanceof File) {
                path = ((File) value).toPath()
            } else if (value instanceof URI) {
                path = Paths.get((URI) value)
            } else if (value instanceof CharSequence) {
                path = Paths.get(value.toString())
            } else {
                fail(
                    "QuPath ScriptAttributes.FILE_PATH has unsupported type " +
                    value.getClass().getName()
                )
            }
        } catch (Exception error) {
            if (error instanceof IllegalStateException &&
                error.message?.startsWith("IFQUANT_PILOT_ERROR:")) {
                throw error
            }
            fail("QuPath ScriptAttributes.FILE_PATH is not a filesystem path")
        }
        return path.toAbsolutePath().normalize()
    }

    static Path packageRelativePath(Path root, String relative) {
        requireSafeRelativePath(relative, "package relative path")
        Path path = root.resolve(relative.replace("/", File.separator)).toAbsolutePath().normalize()
        if (!path.startsWith(root.toAbsolutePath().normalize())) fail("package path escapes output root")
        return path
    }

    static void ensureParentDirectory(Path path) {
        Files.createDirectories(path.getParent())
    }

    static boolean hasSelectedAnnotationAncestor(def pathObject, Set<Object> selected) {
        return selectedAnnotationAncestor(pathObject, selected) != null
    }

    static def selectedAnnotationAncestor(def pathObject, Set<Object> selected) {
        def parent = pathObject.getParent()
        while (parent != null) {
            if (parent.isAnnotation() && selected.contains(parent)) return parent
            parent = parent.getParent()
        }
        return null
    }

    static boolean intersectsAnyAnnotation(def pathObject, List annotations) {
        def roi = pathObject.getROI()
        if (roi == null) return false
        Geometry geometry = roi.getGeometry()
        if (geometry == null || geometry.isEmpty()) return false
        for (def annotation : annotations) {
            def annotationRoi = annotation.getROI()
            if (annotationRoi == null) fail("selected annotation has no ROI")
            Geometry annotationGeometry = annotationRoi.getGeometry()
            if (annotationGeometry == null || annotationGeometry.isEmpty() ||
                !annotationGeometry.isValid()) {
                fail("selected annotation geometry is empty or invalid")
            }
            if (annotationGeometry.intersects(geometry)) return true
        }
        return false
    }

    static Map<String, Object> assignCellToAnnotation(
        def cell,
        List annotations,
        Map<Object, Map<String, Object>> annotationByObject,
        String boundaryPolicy
    ) {
        def cellRoi = cell.getROI()
        if (cellRoi == null) fail("every detected cell requires a cell ROI")
        Geometry cellGeometry = normalizedGeometry(
            cellRoi.getGeometry(),
            "detected cell geometry"
        )
        def nucleusRoi = cell.getNucleusROI()
        Geometry nucleusGeometry = nucleusRoi == null ? null :
            normalizedGeometry(
                nucleusRoi.getGeometry(),
                "detected nucleus geometry"
            )
        boolean nucleusNotCoveredByCell = nucleusGeometry != null &&
            !cellGeometry.covers(nucleusGeometry)
        List<Map<String, Object>> intersections = []
        for (def annotation : annotations) {
            Geometry annotationGeometry = normalizedGeometry(
                annotation.getROI().getGeometry(),
                "selected annotation geometry"
            )
            if (annotationGeometry.intersects(cellGeometry)) {
                intersections.add([
                    annotation: annotation,
                    geometry: annotationGeometry,
                    covers: annotationGeometry.covers(cellGeometry)
                ])
            }
        }
        if (intersections.isEmpty()) {
            return [
                cell: cell,
                cell_geometry: cellGeometry,
                nucleus_geometry: nucleusGeometry,
                annotation: null,
                include: false,
                touches_boundary: false,
                nucleus_not_covered_by_cell_geometry_warning:
                    nucleusNotCoveredByCell,
                exclusion_reason: "no_annotation_intersection"
            ]
        }
        if (intersections.size() > 1) {
            boolean touchesAnyBoundary = intersections.any { intersection ->
                ((Geometry) intersection.get("geometry")).getBoundary()
                    .intersects(cellGeometry)
            }
            return [
                cell: cell,
                cell_geometry: cellGeometry,
                nucleus_geometry: nucleusGeometry,
                annotation: null,
                include: false,
                touches_boundary: touchesAnyBoundary,
                nucleus_not_covered_by_cell_geometry_warning:
                    nucleusNotCoveredByCell,
                exclusion_reason: "ambiguous_annotation_intersection"
            ]
        }
        Map<String, Object> match = intersections.get(0)
        Geometry annotationGeometry =
            (Geometry) match.get("geometry")
        boolean touchesBoundary = annotationGeometry.getBoundary()
            .intersects(cellGeometry)
        boolean annotationCoversCell = (Boolean) match.get("covers")
        boolean include = boundaryPolicyIncludes(
            annotationCoversCell,
            touchesBoundary,
            boundaryPolicy
        )
        if (include && nucleusGeometry == null) {
            fail("an otherwise exportable cell lacks a nucleus ROI")
        }
        boolean annotationCoversNucleus =
            !include || annotationGeometry.covers(nucleusGeometry)
        if (include && !annotationCoversNucleus) {
            include = false
        }
        def annotation = match.get("annotation")
        if (annotationByObject.get(annotation) == null) {
            fail("geometrically assigned annotation lacks a canonical record")
        }
        return [
            cell: cell,
            cell_geometry: cellGeometry,
            nucleus_geometry: nucleusGeometry,
            annotation: annotation,
            include: include,
            touches_boundary: touchesBoundary,
            nucleus_not_covered_by_cell_geometry_warning:
                nucleusNotCoveredByCell,
            exclusion_reason: include ? null : (
                !annotationCoversCell ? "cell_not_covered_by_annotation" :
                touchesBoundary ? "cell_touches_annotation_boundary" :
                "nucleus_not_covered_by_annotation"
            )
        ]
    }

    static boolean boundaryPolicyIncludes(
        boolean annotationCoversCell,
        boolean touchesAnnotationBoundary,
        String boundaryPolicy
    ) {
        if (boundaryPolicy != "exclude_touching_annotation_boundary") {
            fail("unsupported boundary policy reached geometry filter")
        }
        return annotationCoversCell && !touchesAnnotationBoundary
    }

    static Geometry normalizedGeometry(Geometry source, String context) {
        if (source == null || source.isEmpty() || !source.isValid()) fail(context + " is empty or invalid")
        GeometryPrecisionReducer reducer = new GeometryPrecisionReducer(new PrecisionModel(WKT_PRECISION_SCALE))
        reducer.setChangePrecisionModel(true)
        reducer.setRemoveCollapsedComponents(true)
        Geometry normalized = reducer.reduce(source)
        if (normalized == null || normalized.isEmpty() || !normalized.isValid()) fail(context + " failed normalization")
        normalized.normalize()
        String type = normalized.getGeometryType().toUpperCase(Locale.ROOT)
        if (!(type == "POLYGON" || type == "MULTIPOLYGON")) fail(context + " must be polygon or multipolygon")
        return normalized
    }

    static Map<String, Object> wktRecord(Geometry geometry) {
        return [
            encoding: "WKT1",
            geometry_type: geometry.getGeometryType().toUpperCase(Locale.ROOT),
            wkt: new WKTWriter(WKT_DIMENSIONS).write(geometry)
        ]
    }

    static Geometry scaleGeometry(Geometry geometry, double pixelWidth, double pixelHeight) {
        return AffineTransformation.scaleInstance(pixelWidth, pixelHeight).transform(geometry)
    }

    static String canonicalJson(Object value) {
        StringBuilder builder = new StringBuilder()
        appendCanonicalJson(builder, value)
        return builder.toString()
    }

    static void appendCanonicalJson(StringBuilder builder, Object value) {
        if (value == null) {
            builder.append("null")
            return
        }
        if (value instanceof String) {
            rejectUnpairedSurrogates((String) value, "canonical JSON string")
            appendJsonString(builder, (String) value)
            return
        }
        if (value instanceof Boolean) {
            builder.append(value == Boolean.TRUE ? "true" : "false")
            return
        }
        if (value instanceof Number) {
            builder.append(canonicalNumberText((Number) value))
            return
        }
        if (value instanceof Map) {
            List<String> keys = value.keySet().collect {
                if (!(it instanceof String)) {
                    fail("canonical JSON object key is not a string")
                }
                it.toString()
            }.sort()
            builder.append("{")
            boolean first = true
            for (String key : keys) {
                if (!first) builder.append(",")
                first = false
                rejectUnpairedSurrogates(key, "canonical JSON object key")
                appendJsonString(builder, key)
                builder.append(":")
                appendCanonicalJson(builder, value.get(key))
            }
            builder.append("}")
            return
        }
        if (value instanceof Collection) {
            builder.append("[")
            boolean first = true
            for (Object item : (Collection) value) {
                if (!first) builder.append(",")
                first = false
                appendCanonicalJson(builder, item)
            }
            builder.append("]")
            return
        }
        fail("unsupported canonical JSON value type " + value.getClass().getName())
    }

    static void rejectUnpairedSurrogates(String value, String context) {
        for (int index = 0; index < value.length(); index++) {
            char codeUnit = value.charAt(index)
            if (Character.isHighSurrogate(codeUnit)) {
                if (index + 1 >= value.length() ||
                    !Character.isLowSurrogate(value.charAt(index + 1))) {
                    fail(context + " contains an unpaired high surrogate")
                }
                index++
            } else if (Character.isLowSurrogate(codeUnit)) {
                fail(context + " contains an unpaired low surrogate")
            }
        }
    }

    static void appendJsonString(StringBuilder builder, String value) {
        rejectUnpairedSurrogates(value, "JSON string")
        builder.append('"')
        for (int index = 0; index < value.length(); index++) {
            char codeUnit = value.charAt(index)
            switch (codeUnit) {
                case '"' as char:
                    builder.append('\\"')
                    break
                case '\\' as char:
                    builder.append('\\\\')
                    break
                case '\b' as char:
                    builder.append('\\b')
                    break
                case '\f' as char:
                    builder.append('\\f')
                    break
                case '\n' as char:
                    builder.append('\\n')
                    break
                case '\r' as char:
                    builder.append('\\r')
                    break
                case '\t' as char:
                    builder.append('\\t')
                    break
                default:
                    if (codeUnit < 0x20) {
                        builder.append('\\u')
                        builder.append(String.format(Locale.ROOT, '%04x', (int) codeUnit))
                    } else {
                        builder.append(codeUnit)
                    }
            }
        }
        builder.append('"')
    }

    static String jsonString(String value) {
        StringBuilder builder = new StringBuilder()
        appendJsonString(builder, value)
        return builder.toString()
    }

    static String canonicalSha256(Object value) {
        return sha256(canonicalJson(value).getBytes(StandardCharsets.UTF_8))
    }

    static Object canonicalize(Object value) {
        if (value == null || value instanceof String || value instanceof Boolean) return value
        if (value instanceof Map) {
            List<String> keys = value.keySet().collect {
                if (!(it instanceof String)) fail("canonical JSON object key is not a string")
                it.toString()
            }.sort()
            Map<String, Object> sorted = new LinkedHashMap<>()
            for (String key : keys) sorted.put(key, canonicalize(value.get(key)))
            return sorted
        }
        if (value instanceof Collection) return value.collect { canonicalize(it) }
        if (value instanceof Number) return canonicalNumber((Number) value)
        fail("unsupported canonical JSON value type " + value.getClass().getName())
        return null
    }

    static Number canonicalNumber(Number number) {
        String text = canonicalNumberText(number)
        return text.contains(".") ? new BigDecimal(text) : new BigInteger(text)
    }

    static String canonicalNumberText(Number number) {
        double binary64 = number.doubleValue()
        finiteDouble(binary64, "canonical JSON number")
        if (Math.abs(binary64) > MAX_SAFE_INTEGER.doubleValue()) fail("canonical JSON number exceeds safe range")
        if (binary64 == 0.0d && Double.doubleToRawLongBits(binary64) == Double.doubleToRawLongBits(-0.0d)) {
            fail("negative zero is not canonical JSON")
        }
        BigDecimal normalized = BigDecimal.valueOf(binary64).stripTrailingZeros()
        return normalized.signum() == 0 ? "0" : normalized.toPlainString()
    }

    static void verifyCanonicalVectors() {
        List<Map<String, Object>> vectors = [
            [
                name: "unicode-controls-and-small-decimals",
                value: [
                    z: "한글",
                    a: "ä\n\"\\",
                    small: new BigDecimal("1e-7"),
                    less_small: new BigDecimal("1e-5")
                ],
                canonical_utf8:
                    '{"a":"ä\\n\\"\\\\","less_small":0.00001,' +
                    '"small":0.0000001,"z":"한글"}',
                sha256:
                    "552826a2f58ca54e04be7b10fe1c3a349aba62618f370e6d80f384bf60d38111"
            ],
            [
                name: "integral-float-and-nested-unicode",
                value: [
                    integral: 2.0d,
                    fraction: -12.34d,
                    nested: [true, null, "μm²"]
                ],
                canonical_utf8:
                    '{"fraction":-12.34,"integral":2,' +
                    '"nested":[true,null,"μm²"]}',
                sha256:
                    "452d85ac99d2fe777a0511646a392e96f37b79b1a0b73f03914b7b4f75cf7e24"
            ]
        ]
        for (Map<String, Object> vector : vectors) {
            String observed = canonicalJson(vector.get("value"))
            String expected = vector.get("canonical_utf8").toString()
            String observedHash = sha256(observed.getBytes(StandardCharsets.UTF_8))
            if (observed != expected || observedHash != vector.get("sha256")) {
                fail(
                    "internal canonical JSON vector mismatch for " +
                    vector.get("name") + "; expected=" + expected +
                    ", observed=" + observed + ", hash=" + observedHash
                )
            }
        }
    }

    static String sha256(byte[] bytes) {
        return hex(MessageDigest.getInstance("SHA-256").digest(bytes))
    }

    static String sha256File(Path path) {
        MessageDigest digest = MessageDigest.getInstance("SHA-256")
        def stream = Files.newInputStream(path)
        byte[] buffer = new byte[1024 * 1024]
        try {
            int count
            while ((count = stream.read(buffer)) >= 0) {
                if (count > 0) digest.update(buffer, 0, count)
            }
        } finally {
            stream.close()
        }
        return hex(digest.digest())
    }

    static String hex(byte[] bytes) {
        StringBuilder builder = new StringBuilder(bytes.length * 2)
        for (byte value : bytes) builder.append(String.format(Locale.ROOT, "%02x", value & 0xff))
        return builder.toString()
    }

    static String requireQuPathVersion() {
        if (QP.VERSION == null) fail("QuPath runtime version is unavailable")
        return QP.VERSION.toString()
    }

    static void validateProducerProvenance(Map<String, Object> provenance, String context) {
        exactKeys(provenance, ["created_at", "producer_id", "producer_version"], context)
        requireTimestamp(provenance.get("created_at"), context + ".created_at")
        requireIdentifier(provenance.get("producer_id"), context + ".producer_id")
        requireSemver(provenance.get("producer_version"), context + ".producer_version")
    }

    static void validateIntensityDescriptor(Map<String, Object> intensity, String context) {
        exactKeys(intensity, ["representation", "bit_depth", "transform", "scale", "offset", "unit"], context)
        requireEnum(intensity.get("representation"), ["unsigned_integer", "floating_point"], context + ".representation")
        int bitDepth = requireInteger(intensity.get("bit_depth"), context + ".bit_depth", 1)
        if (![8, 16, 32, 64].contains(bitDepth)) fail(context + ".bit_depth is unsupported")
        String transform = requireEnum(intensity.get("transform"), ["none", "linear"], context + ".transform")
        double scale = finiteDouble(intensity.get("scale"), context + ".scale")
        double offset = finiteDouble(intensity.get("offset"), context + ".offset")
        String unit = requireEnum(intensity.get("unit"), ["native_sample_value", "normalized_intensity"], context + ".unit")
        if (transform != "none") {
            fail(
                context + " linear/normalized export is not implemented; " +
                "use transform none with native_sample_value"
            )
        }
        if (transform == "none" && !(scale == 1.0d && offset == 0.0d && unit == "native_sample_value")) {
            fail(context + " transform none requires scale 1, offset 0, native unit")
        }
    }

    static void validateRunQc(Map<String, Object> qc, String context) {
        exactKeys(qc, ["status", "flags"], context)
        requireEnum(qc.get("status"), ["pass", "warn", "fail", "not_evaluated"], context + ".status")
        validateQcFlags(requireList(qc.get("flags"), context + ".flags"), context + ".flags")
    }

    static void validateQcFlags(List flags, String context) {
        Set<String> codes = new HashSet<>()
        for (int index = 0; index < flags.size(); index++) {
            Map<String, Object> flag = requireMap(flags.get(index), context + "[" + index + "]")
            exactKeys(flag, ["code", "severity", "message"], context + "[" + index + "]")
            String code = requireIdentifier(flag.get("code"), context + "[" + index + "].code")
            if (!codes.add(code)) fail("duplicate QC flag code " + code)
            requireEnum(flag.get("severity"), ["info", "warning", "error"], context + "[" + index + "].severity")
            requireResolvedString(flag.get("message"), context + "[" + index + "].message")
        }
    }

    static void appendExporterQcFlag(
        List<Map<String, Object>> flags,
        Map<String, Object> addition
    ) {
        String code = addition.get("code").toString()
        if (flags.any { it.get("code") == code }) {
            fail("configured QC flag collides with exporter-reserved code " + code)
        }
        flags.add(addition)
    }

    static void appendExclusionQcFlags(
        List<Map<String, Object>> flags,
        Map<String, Integer> exclusionCounts
    ) {
        Map<String, String> descriptions = [
            ambiguous_annotation_intersection:
                "intersected more than one selected annotation",
            cell_not_covered_by_annotation:
                "crossed outside its selected annotation",
            cell_touches_annotation_boundary:
                "touched its selected annotation boundary",
            no_annotation_intersection:
                "did not intersect a selected annotation",
            nucleus_not_covered_by_annotation:
                "had a nucleus outside its selected annotation"
        ]
        for (String reason : new TreeSet<>(exclusionCounts.keySet())) {
            Integer count = exclusionCounts.get(reason)
            if (!descriptions.containsKey(reason) || count == null || count <= 0) {
                fail("invalid internal cell-exclusion ledger")
            }
            appendExporterQcFlag(flags, [
                code: "cells_excluded_" + reason,
                severity: "warning",
                message: count + " detected cell(s) " +
                    descriptions.get(reason) + " and were excluded."
            ])
        }
    }

    static Map<String, Integer> countObjectQcFlags(
        List<Map<String, Object>> records
    ) {
        Map<String, Integer> counts = new TreeMap<>()
        for (Map<String, Object> record : records) {
            Map<String, Object> qc = requireMap(
                record.get("qc"),
                "generated cell_object.qc"
            )
            List<Map<String, Object>> flags = typedMapList(
                requireList(qc.get("flags"), "generated cell_object.qc.flags"),
                "generated cell_object.qc.flags"
            )
            for (Map<String, Object> flag : flags) {
                String code = flag.get("code").toString()
                counts.put(code, (counts.get(code) ?: 0) + 1)
            }
        }
        return counts
    }

    static void validateMorphologyCombination(String compartment, String feature, String unit, String context) {
        if (feature == "area" && unit != "um2") fail(context + " area requires um2")
        if (feature == "perimeter" && unit != "um") fail(context + " perimeter requires um")
        if (["circularity", "nucleus_cell_area_ratio"].contains(feature) && unit != "ratio") {
            fail(context + " ratio feature requires ratio unit")
        }
        if (feature == "nucleus_cell_area_ratio" && compartment != "nucleus") {
            fail(context + " nucleus/cell ratio uses nucleus compartment")
        }
    }

    static double positiveGeometryValue(Object value, String context) {
        double number = finiteDouble(value, context)
        if (number <= 0.0d) fail(context + " must be positive")
        return number
    }

    static double boundedRatio(Object value, String context) {
        double number = finiteDouble(value, context)
        if (number < 0.0d || number > 1.0d + 1.0e-12d) fail(context + " is outside [0, 1]")
        return Math.min(1.0d, number)
    }

    static double finiteDouble(Object value, String context) {
        if (!(value instanceof Number)) fail(context + " is not numeric")
        double number = ((Number) value).doubleValue()
        if (!Double.isFinite(number)) fail(context + " is not finite")
        return number == 0.0d ? 0.0d : number
    }

    static double requirePositiveDouble(Object value, String context) {
        double number = finiteDouble(value, context)
        if (number <= 0.0d) fail(context + " must be positive")
        return number
    }

    static double requireNonnegativeDouble(Object value, String context) {
        double number = finiteDouble(value, context)
        if (number < 0.0d) fail(context + " must be nonnegative")
        return number
    }

    static boolean requireBoolean(Object value, String context) {
        if (!(value instanceof Boolean)) fail(context + " must be boolean")
        return (Boolean) value
    }

    static int requireInteger(Object value, String context, int minimum) {
        if (!(value instanceof Number) || value instanceof Boolean) fail(context + " must be an integer")
        int integer
        try {
            integer = new BigDecimal(value.toString()).intValueExact()
        } catch (ArithmeticException error) {
            fail(context + " must be a 32-bit integer")
            return 0
        }
        if (integer < minimum) fail(context + " is below minimum")
        return integer
    }

    static long requireNonnegativeSafeLong(Object value, String context) {
        if (!(value instanceof Number) || value instanceof Boolean) {
            fail(context + " must be an integer")
        }
        BigInteger integer
        try {
            integer = new BigDecimal(value.toString()).toBigIntegerExact()
        } catch (ArithmeticException error) {
            fail(context + " must be an integer")
            return 0L
        }
        if (integer.signum() < 0 || integer.compareTo(MAX_SAFE_INTEGER) > 0) {
            fail(context + " must be in [0, 9007199254740991]")
        }
        return integer.longValueExact()
    }

    static String requireResolvedString(Object value, String context) {
        if (!(value instanceof String)) fail(context + " must be a string")
        String text = value.toString()
        if (text.trim().isEmpty()) fail(context + " must not be blank")
        if (text.contains("<") || text.contains(">")) fail(context + " contains an unresolved placeholder")
        return text
    }

    static String requireIdentifier(Object value, String context) {
        String text = requireResolvedString(value, context)
        if (!IDENTIFIER.matcher(text).matches()) fail(context + " is not a valid identifier")
        return text
    }

    static void requireNullableIdentifier(Object value, String context) {
        if (value != null) requireIdentifier(value, context)
    }

    static String requireSemver(Object value, String context) {
        String text = requireResolvedString(value, context)
        if (!SEMVER.matcher(text).matches()) fail(context + " is not semver")
        return text
    }

    static String requireCodeRevision(Object value, String context) {
        String text = requireResolvedString(value, context)
        if (!CODE_REVISION.matcher(text).matches()) fail(context + " must be 7-64 lowercase hexadecimal characters")
        return text
    }

    static String requireSha256(Object value, String context) {
        String text = requireResolvedString(value, context)
        if (!SHA256.matcher(text).matches() || text ==~ /0{64}/) {
            fail(context + " must be a nonzero lowercase SHA-256")
        }
        return text
    }

    static String requireSafeRelativePath(Object value, String context) {
        String text = requireResolvedString(value, context)
        if (text.contains("\\") || text.startsWith("/") || text ==~ /^[A-Za-z]:.*/ || text.split("/").contains("..")) {
            fail(context + " must be a safe package-relative path using /")
        }
        return text
    }

    static Instant requireTimestamp(Object value, String context) {
        String text = requireResolvedString(value, context)
        if (!text.endsWith("Z")) fail(context + " must end in Z")
        try {
            return Instant.parse(text)
        } catch (Exception error) {
            fail(context + " is not an RFC 3339 UTC timestamp")
            return null
        }
    }

    static void requireNullableTimestamp(Object value, String context) {
        if (value != null) requireTimestamp(value, context)
    }

    static String requireEnum(Object value, Collection<String> allowed, String context) {
        String text = requireResolvedString(value, context)
        if (!allowed.contains(text)) fail(context + " has unsupported value")
        return text
    }

    static void requireExactString(Object value, String expected, String context) {
        String actual = requireResolvedString(value, context)
        if (actual != expected) fail(context + " must equal " + quoted(expected))
    }

    static Map<String, Object> requireMap(Object value, String context) {
        if (!(value instanceof Map)) fail(context + " must be a JSON object")
        return (Map<String, Object>) value
    }

    static List requireList(Object value, String context) {
        if (!(value instanceof List)) fail(context + " must be a JSON array")
        return (List) value
    }

    static List<Map<String, Object>> typedMapList(List values, String context) {
        List<Map<String, Object>> result = []
        for (int index = 0; index < values.size(); index++) {
            result.add(requireMap(values.get(index), context + "[" + index + "]"))
        }
        return result
    }

    static void exactKeys(Map<String, Object> map, Collection<String> expected, String context) {
        Set<String> expectedSet = new TreeSet<>(expected)
        Set<String> actualSet = new TreeSet<>(map.keySet())
        if (actualSet != expectedSet) {
            Set<String> missing = new TreeSet<>(expectedSet)
            missing.removeAll(actualSet)
            Set<String> unknown = new TreeSet<>(actualSet)
            unknown.removeAll(expectedSet)
            fail(context + " fields mismatch; missing=" + missing + ", unknown=" + unknown)
        }
    }

    static String quoted(String value) {
        return jsonString(value)
    }
}

Object ifquantExecutingScriptPath = null
try {
    ifquantExecutingScriptPath = getProperty(ScriptAttributes.FILE_PATH)
} catch (MissingPropertyException ignored) {
    // The exporter reports a fail-closed error with the required attribute name.
}
IfQuantV1Exporter.run(
    args == null ? new String[0] : (args as String[]),
    ifquantExecutingScriptPath
)
