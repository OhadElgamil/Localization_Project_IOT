import 'package:flutter/foundation.dart' show listEquals;
import 'package:flutter/material.dart';
import '../models/aruco_marker.dart';
import '../models/room_bounds.dart';

/// Draws a top-down 2D room map: the calibrated markers' bounding rectangle,
/// each marker as a labeled dot, and the live/frozen predicted position.
class RoomMapPainter extends CustomPainter {
  final RoomBounds bounds;
  final List<ArucoMarker> markers;
  final double? posX;
  final double? posZ;
  // True when the latest poll didn't produce a fresh fix -- the dot is drawn
  // static and dim instead of blinking, to visually distinguish "last known"
  // from "live".
  final bool isFrozen;
  final double blinkOpacity;
  final ColorScheme colorScheme;

  static const _padding = 24.0;
  static const _markerRadius = 4.0;
  static const _positionRadius = 8.0;

  RoomMapPainter({
    required this.bounds,
    required this.markers,
    required this.posX,
    required this.posZ,
    required this.isFrozen,
    required this.blinkOpacity,
    required this.colorScheme,
  });

  // Inset by padding, then letterbox to the room's aspect ratio so it isn't
  // stretched to fill a differently-shaped canvas.
  Rect _letterboxedRect(Size size) {
    final available = Rect.fromLTWH(
      _padding,
      _padding,
      size.width - _padding * 2,
      size.height - _padding * 2,
    );
    if (available.width <= 0 || available.height <= 0) return available;
    final roomAspect = bounds.width / bounds.height;
    final availableAspect = available.width / available.height;
    double w = available.width;
    double h = available.height;
    if (roomAspect > availableAspect) {
      h = w / roomAspect;
    } else {
      w = h * roomAspect;
    }
    final left = available.left + (available.width - w) / 2;
    final top = available.top + (available.height - h) / 2;
    return Rect.fromLTWH(left, top, w, h);
  }

  // Z increasing maps to canvas Y decreasing (top-down: +Z is "up" on the
  // page), since canvas Y grows downward.
  Offset _toCanvas(Rect rect, double x, double z) {
    final u = (x - bounds.minX) / bounds.width;
    final v = (z - bounds.minZ) / bounds.height;
    return Offset(rect.left + u * rect.width, rect.bottom - v * rect.height);
  }

  @override
  void paint(Canvas canvas, Size size) {
    final rect = _letterboxedRect(size);
    if (rect.width <= 0 || rect.height <= 0) return;

    canvas.drawRect(
      rect,
      Paint()
        ..color = colorScheme.outline
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );

    final markerPaint = Paint()..color = colorScheme.primary;
    for (final marker in markers) {
      final p = _toCanvas(rect, marker.x, marker.z);
      canvas.drawCircle(p, _markerRadius, markerPaint);
      final label = TextPainter(
        text: TextSpan(
          text: '#${marker.markerId}',
          style: TextStyle(color: colorScheme.primary, fontSize: 11),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      label.paint(canvas, p + const Offset(6, -6));
    }

    final x = posX;
    final z = posZ;
    if (x != null && z != null) {
      final p = _toCanvas(rect, x, z);
      final dotColor = isFrozen
          ? colorScheme.outline.withValues(alpha: 0.5)
          : Colors.red.withValues(alpha: 0.4 + 0.6 * blinkOpacity);
      canvas.drawCircle(p, _positionRadius, Paint()..color = dotColor);
      canvas.drawCircle(
        p,
        _positionRadius + 3,
        Paint()
          ..color = dotColor
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2,
      );
    }
  }

  @override
  bool shouldRepaint(covariant RoomMapPainter oldDelegate) {
    return bounds != oldDelegate.bounds ||
        !listEquals(markers, oldDelegate.markers) ||
        posX != oldDelegate.posX ||
        posZ != oldDelegate.posZ ||
        isFrozen != oldDelegate.isFrozen ||
        blinkOpacity != oldDelegate.blinkOpacity;
  }
}

class RoomMapView extends StatelessWidget {
  final RoomBounds bounds;
  final List<ArucoMarker> markers;
  final double? posX;
  final double? posZ;
  final bool isFrozen;
  final double blinkOpacity;

  const RoomMapView({
    super.key,
    required this.bounds,
    required this.markers,
    required this.posX,
    required this.posZ,
    required this.isFrozen,
    required this.blinkOpacity,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return LayoutBuilder(
      builder: (context, constraints) => CustomPaint(
        size: Size(constraints.maxWidth, constraints.maxHeight),
        painter: RoomMapPainter(
          bounds: bounds,
          markers: markers,
          posX: posX,
          posZ: posZ,
          isFrozen: isFrozen,
          blinkOpacity: blinkOpacity,
          colorScheme: colorScheme,
        ),
      ),
    );
  }
}
