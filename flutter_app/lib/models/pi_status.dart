class PiStatus {
  final bool isOnline;
  final int connectedCameras;
  final int markersLoaded;
  final String? version;

  const PiStatus({
    required this.isOnline,
    required this.connectedCameras,
    required this.markersLoaded,
    this.version,
  });

  factory PiStatus.offline() => const PiStatus(
        isOnline: false,
        connectedCameras: 0,
        markersLoaded: 0,
      );

  factory PiStatus.fromJson(Map<String, dynamic> json) => PiStatus(
        isOnline: true,
        connectedCameras: (json['connected_cameras'] as num?)?.toInt() ?? 0,
        markersLoaded: (json['markers_loaded'] as num?)?.toInt() ?? 0,
        version: json['version'] as String?,
      );
}
