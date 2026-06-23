import 'dart:convert';

class ArucoMarker {
  final int markerId;
  final double x;
  final double y;
  final double z;

  const ArucoMarker({
    required this.markerId,
    required this.x,
    required this.y,
    required this.z,
  });

  Map<String, dynamic> toJson() => {
        'id': markerId,
        'x': x,
        'y': y,
        'z': z,
      };

  factory ArucoMarker.fromJson(Map<String, dynamic> json) => ArucoMarker(
        markerId: (json['id'] as num).toInt(),
        x: (json['x'] as num).toDouble(),
        y: (json['y'] as num).toDouble(),
        z: (json['z'] as num).toDouble(),
      );

  ArucoMarker copyWith({int? markerId, double? x, double? y, double? z}) {
    return ArucoMarker(
      markerId: markerId ?? this.markerId,
      x: x ?? this.x,
      y: y ?? this.y,
      z: z ?? this.z,
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
  String toString() => 'ArucoMarker(id: $markerId, x: $x, y: $y, z: $z)';
}
