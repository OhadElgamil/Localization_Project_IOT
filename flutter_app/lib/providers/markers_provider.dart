import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/aruco_marker.dart';
import '../models/room_bounds.dart';

class MarkersProvider extends ChangeNotifier {
  static const _keyMarkers = 'aruco_markers';

  final List<ArucoMarker> _markers = [];
  bool _isLoading = false;

  List<ArucoMarker> get markers => List.unmodifiable(_markers);
  bool get isLoading => _isLoading;
  bool get hasMarkers => _markers.isNotEmpty;

  // Null whenever a room rectangle can't be formed: fewer than 2 markers, or
  // every marker shares the same X or the same Z (collinear -> zero-width or
  // zero-height rectangle). Callers use markers.length to pick the right
  // "why not" message.
  RoomBounds? get roomBounds {
    if (_markers.length < 2) return null;
    double minX = _markers.first.x;
    double maxX = _markers.first.x;
    double minZ = _markers.first.z;
    double maxZ = _markers.first.z;
    for (final m in _markers.skip(1)) {
      if (m.x < minX) minX = m.x;
      if (m.x > maxX) maxX = m.x;
      if (m.z < minZ) minZ = m.z;
      if (m.z > maxZ) maxZ = m.z;
    }
    final bounds = RoomBounds(minX: minX, maxX: maxX, minZ: minZ, maxZ: maxZ);
    return bounds.isDegenerate ? null : bounds;
  }

  MarkersProvider() {
    _loadLocal();
  }

  Future<void> _loadLocal() async {
    _isLoading = true;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    final data = prefs.getString(_keyMarkers);
    if (data != null) {
      final list = jsonDecode(data) as List;
      _markers.clear();
      _markers.addAll(
        list.map((e) => ArucoMarker.fromJson(e as Map<String, dynamic>)),
      );
    }
    _isLoading = false;
    notifyListeners();
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _keyMarkers,
      jsonEncode(_markers.map((m) => m.toJson()).toList()),
    );
  }

  void _sort() => _markers.sort((a, b) => a.markerId.compareTo(b.markerId));

  bool hasId(int id) => _markers.any((m) => m.markerId == id);

  void addOrUpdateMarker(ArucoMarker marker) {
    final idx = _markers.indexWhere((m) => m.markerId == marker.markerId);
    if (idx >= 0) {
      _markers[idx] = marker;
    } else {
      _markers.add(marker);
    }
    _sort();
    _persist();
    notifyListeners();
  }

  void removeMarker(int markerId) {
    _markers.removeWhere((m) => m.markerId == markerId);
    _persist();
    notifyListeners();
  }

  void clearAll() {
    _markers.clear();
    _persist();
    notifyListeners();
  }

  void replaceAll(List<ArucoMarker> markers) {
    _markers.clear();
    _markers.addAll(markers);
    _sort();
    _persist();
    notifyListeners();
  }
}
