import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/aruco_marker.dart';
import '../providers/markers_provider.dart';
import 'add_edit_marker_screen.dart';

class MarkersScreen extends StatelessWidget {
  const MarkersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('ArUco Markers'),
        backgroundColor: cs.primaryContainer,
        foregroundColor: cs.onPrimaryContainer,
        actions: [
          Consumer<MarkersProvider>(
            builder: (_, provider, __) => provider.hasMarkers
                ? IconButton(
                    icon: const Icon(Icons.delete_sweep_outlined),
                    tooltip: 'Clear all',
                    onPressed: () => _confirmClearAll(context, provider),
                  )
                : const SizedBox.shrink(),
          ),
        ],
      ),
      body: Consumer<MarkersProvider>(
        builder: (context, provider, _) {
          if (provider.isLoading) {
            return const Center(child: CircularProgressIndicator());
          }
          if (!provider.hasMarkers) {
            return _EmptyState(
              onAdd: () => _openAddScreen(context),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.symmetric(vertical: 8),
            itemCount: provider.markers.length,
            separatorBuilder: (_, __) => const Divider(height: 1, indent: 72),
            itemBuilder: (context, index) {
              final marker = provider.markers[index];
              return _MarkerTile(
                marker: marker,
                onEdit: () => _openEditScreen(context, marker),
                onDelete: () => _confirmDelete(context, provider, marker),
              );
            },
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _openAddScreen(context),
        icon: const Icon(Icons.add),
        label: const Text('Add Marker'),
      ),
    );
  }

  void _openAddScreen(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const AddEditMarkerScreen()),
    );
  }

  void _openEditScreen(BuildContext context, ArucoMarker marker) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => AddEditMarkerScreen(existing: marker),
      ),
    );
  }

  void _confirmDelete(
      BuildContext context, MarkersProvider provider, ArucoMarker marker) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Marker?'),
        content: Text('Remove marker #${marker.markerId} from the list?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              provider.removeMarker(marker.markerId);
              Navigator.pop(ctx);
            },
            child: const Text('Delete'),
          ),
        ],
      ),
    );
  }

  void _confirmClearAll(BuildContext context, MarkersProvider provider) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clear All Markers?'),
        content: const Text('This will remove all configured markers.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
            onPressed: () {
              provider.clearAll();
              Navigator.pop(ctx);
            },
            child: const Text('Clear All'),
          ),
        ],
      ),
    );
  }
}

class _MarkerTile extends StatelessWidget {
  final ArucoMarker marker;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  const _MarkerTile({
    required this.marker,
    required this.onEdit,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: cs.primaryContainer,
        child: Text(
          '#${marker.markerId}',
          style: TextStyle(
            color: cs.onPrimaryContainer,
            fontWeight: FontWeight.bold,
            fontSize: 12,
          ),
        ),
      ),
      title: Text('Marker ${marker.markerId}'),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'X: ${marker.x.toStringAsFixed(3)}  '
            'Y: ${marker.y.toStringAsFixed(3)}  '
            'Z: ${marker.z.toStringAsFixed(3)}',
            style: const TextStyle(fontFamily: 'monospace'),
          ),
          if (marker.rollDeg != 0 || marker.pitchDeg != 0 || marker.yawDeg != 0)
            Text(
              'R: ${marker.rollDeg.toStringAsFixed(1)}°  '
              'P: ${marker.pitchDeg.toStringAsFixed(1)}°  '
              'Y: ${marker.yawDeg.toStringAsFixed(1)}°',
              style: const TextStyle(fontFamily: 'monospace'),
            ),
        ],
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            icon: const Icon(Icons.edit_outlined),
            onPressed: onEdit,
            tooltip: 'Edit',
          ),
          IconButton(
            icon: Icon(Icons.delete_outline,
                color: cs.error),
            onPressed: onDelete,
            tooltip: 'Delete',
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final VoidCallback onAdd;

  const _EmptyState({required this.onAdd});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.qr_code_2, size: 80, color: cs.outlineVariant),
          const SizedBox(height: 16),
          Text(
            'No markers configured',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text(
            'Add ArUco markers with their real-world positions.',
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: cs.outline),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: onAdd,
            icon: const Icon(Icons.add),
            label: const Text('Add First Marker'),
          ),
        ],
      ),
    );
  }
}
