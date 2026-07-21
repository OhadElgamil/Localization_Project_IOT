class LocalizationResult {
  final double x;
  final double y;
  final double z;
  final double? yaw;
  final double confidence;
  final DateTime timestamp;
  final int markersDetected;
  final List<int> markerIds;
  // Most recent completed SNAP round-trip time per camera name, in seconds.
  // A missing entry or null value means that camera hasn't responded yet
  // this cycle (still in flight) -- it's not disconnected, just slow.
  final Map<String, double?> cameraResponseTimes;
  // The pipeline's own cycle rate (sample + detect + localize + post),
  // windowed-averaged pipeline-side (see pipeline/fps_tracker.py). Null
  // means the pipeline hasn't reported one yet (just started, or the
  // connection is stale -- see pi_server/server.py's staleness check).
  final double? fps;
  // Set when the Pi couldn't compute a position this cycle (e.g. fewer than
  // 3 barcodes visible) -- x/y/z/yaw are meaningless (zeroed) when this is set.
  final String? error;

  const LocalizationResult({
    required this.x,
    required this.y,
    required this.z,
    this.yaw,
    required this.confidence,
    required this.timestamp,
    required this.markersDetected,
    this.markerIds = const [],
    this.cameraResponseTimes = const {},
    this.fps,
    this.error,
  });

  factory LocalizationResult.fromJson(Map<String, dynamic> json) {
    final pos = json['position'] as Map<String, dynamic>?;
    final orient = json['orientation'] as Map<String, dynamic>?;
    final times = json['camera_response_times_s'] as Map<String, dynamic>?;
    return LocalizationResult(
      x: (pos?['x'] as num? ?? 0).toDouble(),
      y: (pos?['y'] as num? ?? 0).toDouble(),
      z: (pos?['z'] as num? ?? 0).toDouble(),
      yaw: orient != null ? (orient['yaw'] as num?)?.toDouble() : null,
      confidence: (json['confidence'] as num? ?? 0.0).toDouble(),
      timestamp: json['timestamp'] != null
          ? DateTime.tryParse(json['timestamp'] as String) ?? DateTime.now()
          : DateTime.now(),
      markersDetected: (json['markers_detected'] as num? ?? 0).toInt(),
      markerIds: (json['marker_ids'] as List<dynamic>? ?? const [])
          .map((e) => (e as num).toInt())
          .toList(),
      cameraResponseTimes: (times ?? const {})
          .map((name, v) => MapEntry(name, (v as num?)?.toDouble())),
      fps: (json['fps'] as num?)?.toDouble(),
      error: json['error'] as String?,
    );
  }
}
