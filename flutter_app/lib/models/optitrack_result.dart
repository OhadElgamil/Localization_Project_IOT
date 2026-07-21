class OptiTrackResult {
  final double estimateX;
  final double estimateY;
  final double estimateZ;
  final double groundTruthX;
  final double groundTruthY;
  final double groundTruthZ;
  final double errorM;
  // Number of times the OptiTrack server had to retry its (flaky,
  // third-party) OptiTrack call before it got an answer. Debug-only signal.
  final int failedAttempts;
  final DateTime timestamp;

  const OptiTrackResult({
    required this.estimateX,
    required this.estimateY,
    required this.estimateZ,
    required this.groundTruthX,
    required this.groundTruthY,
    required this.groundTruthZ,
    required this.errorM,
    required this.failedAttempts,
    required this.timestamp,
  });

  factory OptiTrackResult.fromJson(Map<String, dynamic> json) {
    final estimate = _xyz(json['estimate']);
    final groundTruth = _xyz(json['ground_truth']);
    return OptiTrackResult(
      estimateX: estimate.$1,
      estimateY: estimate.$2,
      estimateZ: estimate.$3,
      groundTruthX: groundTruth.$1,
      groundTruthY: groundTruth.$2,
      groundTruthZ: groundTruth.$3,
      errorM: (json['error_m'] as num).toDouble(),
      failedAttempts: (json['failed_attempts'] as num? ?? 0).toInt(),
      timestamp: json['timestamp'] != null
          ? DateTime.tryParse(json['timestamp'] as String) ?? DateTime.now()
          : DateTime.now(),
    );
  }

  // The server forwards whatever query_optitrack() on the OptiTrack side
  // returns for ground_truth -- some OptiTrack/NatNet clients hand back a
  // plain [x, y, z] list rather than a {"x":..,"y":..,"z":..} object, so
  // this accepts either shape instead of assuming one.
  static (double, double, double) _xyz(dynamic value) {
    if (value is Map) {
      return (
        (value['x'] as num).toDouble(),
        (value['y'] as num).toDouble(),
        (value['z'] as num).toDouble(),
      );
    }
    if (value is List && value.length >= 3) {
      return (
        (value[0] as num).toDouble(),
        (value[1] as num).toDouble(),
        (value[2] as num).toDouble(),
      );
    }
    throw FormatException(
        'Expected a position as {x,y,z} or [x,y,z], got: $value');
  }
}
