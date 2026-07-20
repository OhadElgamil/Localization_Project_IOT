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
    final estimate = json['estimate'] as Map<String, dynamic>;
    final groundTruth = json['ground_truth'] as Map<String, dynamic>;
    return OptiTrackResult(
      estimateX: (estimate['x'] as num).toDouble(),
      estimateY: (estimate['y'] as num).toDouble(),
      estimateZ: (estimate['z'] as num).toDouble(),
      groundTruthX: (groundTruth['x'] as num).toDouble(),
      groundTruthY: (groundTruth['y'] as num).toDouble(),
      groundTruthZ: (groundTruth['z'] as num).toDouble(),
      errorM: (json['error_m'] as num).toDouble(),
      failedAttempts: (json['failed_attempts'] as num? ?? 0).toInt(),
      timestamp: json['timestamp'] != null
          ? DateTime.tryParse(json['timestamp'] as String) ?? DateTime.now()
          : DateTime.now(),
    );
  }
}
