import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/aruco_marker.dart';

class MarkersProvider extends ChangeNotifier {
  static const _keyMarkers = 'aruco_markers';

  final List<ArucoMarker> _markers = [];
  bool _isLoading = false;

  List<ArucoMarker> get markers => List.unmodifiable(_markers);
  bool get isLoading => _isLoading;
  bool get hasMarkers => _markers.isNotEmpty;

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
