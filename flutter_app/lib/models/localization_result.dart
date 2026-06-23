class LocalizationResult {
  final double x;
  final double y;
  final double z;
  final double? yaw;
  final double confidence;
  final DateTime timestamp;
  final int markersDetected;

  const LocalizationResult({
    required this.x,
    required this.y,
    required this.z,
    this.yaw,
    required this.confidence,
    required this.timestamp,
    required this.markersDetected,
  });

  factory LocalizationResult.fromJson(Map<String, dynamic> json) {
    final pos = json['position'] as Map<String, dynamic>? ?? json;
    final orient = json['orientation'] as Map<String, dynamic>?;
    return LocalizationResult(
      x: (pos['x'] as num).toDouble(),
      y: (pos['y'] as num).toDouble(),
      z: (pos['z'] as num? ?? 0).toDouble(),
      yaw: orient != null ? (orient['yaw'] as num?)?.toDouble() : null,
      confidence: (json['confidence'] as num? ?? 0.0).toDouble(),
      timestamp: json['timestamp'] != null
          ? DateTime.tryParse(json['timestamp'] as String) ?? DateTime.now()
          : DateTime.now(),
      markersDetected: (json['markers_detected'] as num? ?? 0).toInt(),
    );
  }
}
