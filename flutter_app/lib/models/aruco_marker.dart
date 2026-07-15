import 'dart:convert';

class ArucoMarker {
  final int markerId;
  final double x;
  final double y;
  final double z;
  // Orientation of the marker itself in the room, degrees. Defaults to 0
  // (marker faces "straight forward" in the world frame) for markers that
  // were placed before orientation support existed, or for markers that
  // genuinely are mounted with no rotation.
  final double rollDeg;
  final double pitchDeg;
  final double yawDeg;

  const ArucoMarker({
    required this.markerId,
    required this.x,
    required this.y,
    required this.z,
    this.rollDeg = 0.0,
    this.pitchDeg = 0.0,
    this.yawDeg = 0.0,
  });

  Map<String, dynamic> toJson() => {
        'id': markerId,
        'x': x,
        'y': y,
        'z': z,
        'roll_deg': rollDeg,
        'pitch_deg': pitchDeg,
        'yaw_deg': yawDeg,
      };

  factory ArucoMarker.fromJson(Map<String, dynamic> json) => ArucoMarker(
        markerId: (json['id'] as num).toInt(),
        x: (json['x'] as num).toDouble(),
        y: (json['y'] as num).toDouble(),
        z: (json['z'] as num).toDouble(),
        rollDeg: (json['roll_deg'] as num?)?.toDouble() ?? 0.0,
        pitchDeg: (json['pitch_deg'] as num?)?.toDouble() ?? 0.0,
        yawDeg: (json['yaw_deg'] as num?)?.toDouble() ?? 0.0,
      );

  ArucoMarker copyWith({
    int? markerId,
    double? x,
    double? y,
    double? z,
    double? rollDeg,
    double? pitchDeg,
    double? yawDeg,
  }) {
    return ArucoMarker(
      markerId: markerId ?? this.markerId,
      x: x ?? this.x,
      y: y ?? this.y,
      z: z ?? this.z,
      rollDeg: rollDeg ?? this.rollDeg,
      pitchDeg: pitchDeg ?? this.pitchDeg,
      yawDeg: yawDeg ?? this.yawDeg,
    );
  }

  String toStorageString() => jsonEncode(toJson());

  factory ArucoMarker.fromStorageString(String s) =>
      ArucoMarker.fromJson(jsonDecode(s) as Map<String, dynamic>);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ArucoMarker && markerId == other.markerId;

  @override
  int get hashCode => markerId.hashCode;

  @override
  String toString() =>
      'ArucoMarker(id: $markerId, x: $x, y: $y, z: $z, roll: $rollDeg, pitch: $pitchDeg, yaw: $yawDeg)';
}
