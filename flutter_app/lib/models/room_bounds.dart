/// Bounding rectangle of the room's floor plane (X/Z), derived from the
/// extremes of the calibrated ArUco markers.
class RoomBounds {
  final double minX;
  final double maxX;
  final double minZ;
  final double maxZ;

  const RoomBounds({
    required this.minX,
    required this.maxX,
    required this.minZ,
    required this.maxZ,
  });

  double get width => maxX - minX;
  double get height => maxZ - minZ;

  bool get isDegenerate => width <= 0 || height <= 0;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RoomBounds &&
          minX == other.minX &&
          maxX == other.maxX &&
          minZ == other.minZ &&
          maxZ == other.maxZ;

  @override
  int get hashCode => Object.hash(minX, maxX, minZ, maxZ);
}
