import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../models/aruco_marker.dart';
import '../providers/markers_provider.dart';

class AddEditMarkerScreen extends StatefulWidget {
  final ArucoMarker? existing;

  const AddEditMarkerScreen({super.key, this.existing});

  @override
  State<AddEditMarkerScreen> createState() => _AddEditMarkerScreenState();
}

class _AddEditMarkerScreenState extends State<AddEditMarkerScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _idCtrl;
  late final TextEditingController _xCtrl;
  late final TextEditingController _yCtrl;
  late final TextEditingController _zCtrl;
  late final TextEditingController _rollCtrl;
  late final TextEditingController _pitchCtrl;
  late final TextEditingController _yawCtrl;

  bool get _isEditing => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final m = widget.existing;
    _idCtrl = TextEditingController(text: m != null ? '${m.markerId}' : '');
    _xCtrl = TextEditingController(text: m != null ? '${m.x}' : '');
    _yCtrl = TextEditingController(text: m != null ? '${m.y}' : '');
    _zCtrl = TextEditingController(text: m != null ? '${m.z}' : '');
    _rollCtrl = TextEditingController(text: '${m?.rollDeg ?? 0.0}');
    _pitchCtrl = TextEditingController(text: '${m?.pitchDeg ?? 0.0}');
    _yawCtrl = TextEditingController(text: '${m?.yawDeg ?? 0.0}');
  }

  @override
  void dispose() {
    _idCtrl.dispose();
    _xCtrl.dispose();
    _yCtrl.dispose();
    _zCtrl.dispose();
    _rollCtrl.dispose();
    _pitchCtrl.dispose();
    _yawCtrl.dispose();
    super.dispose();
  }

  void _save() {
    if (!_formKey.currentState!.validate()) return;

    final provider = context.read<MarkersProvider>();
    final markerId = int.parse(_idCtrl.text.trim());
    final x = double.parse(_xCtrl.text.trim());
    final y = double.parse(_yCtrl.text.trim());
    final z = double.parse(_zCtrl.text.trim());
    final roll = double.parse(_rollCtrl.text.trim());
    final pitch = double.parse(_pitchCtrl.text.trim());
    final yaw = double.parse(_yawCtrl.text.trim());

    if (!_isEditing && provider.hasId(markerId)) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Marker ID $markerId already exists.'),
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );
      return;
    }

    final marker = ArucoMarker(
      markerId: markerId,
      x: x,
      y: y,
      z: z,
      rollDeg: roll,
      pitchDeg: pitch,
      yawDeg: yaw,
    );
    provider.addOrUpdateMarker(marker);
    Navigator.of(context).pop();
  }

  String? _validateDouble(String? v) {
    if (v == null || v.trim().isEmpty) return 'Required';
    if (double.tryParse(v.trim()) == null) return 'Enter a valid number';
    return null;
  }

  String? _validateId(String? v) {
    if (v == null || v.trim().isEmpty) return 'Required';
    final n = int.tryParse(v.trim());
    if (n == null) return 'Enter a valid integer';
    if (n < 0 || n > 1023) return 'ID must be 0–1023';
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text(_isEditing ? 'Edit Marker' : 'Add Marker'),
        backgroundColor: cs.primaryContainer,
        foregroundColor: cs.onPrimaryContainer,
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            _CoordField(
              controller: _idCtrl,
              label: 'Marker ID',
              hint: '0–1023',
              icon: Icons.tag,
              readOnly: _isEditing,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              validator: _validateId,
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 4),
            Text(
              'The room\'s (0, 0, 0) is its center, so most markers will need '
              'negative X or Z -- tap the +/- button to flip the sign.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.outline,
                  ),
            ),
            const SizedBox(height: 16),
            _buildSectionLabel(context, 'Position (meters, Y is up)'),
            const SizedBox(height: 12),
            _CoordField(
              controller: _xCtrl,
              label: 'X',
              hint: 'e.g. -1.50',
              icon: Icons.arrow_right_alt,
              validator: _validateDouble,
              allowNegative: true,
            ),
            const SizedBox(height: 12),
            _CoordField(
              controller: _yCtrl,
              label: 'Y (up)',
              hint: 'e.g. 0.00',
              icon: Icons.arrow_upward,
              validator: _validateDouble,
              allowNegative: true,
            ),
            const SizedBox(height: 12),
            _CoordField(
              controller: _zCtrl,
              label: 'Z',
              hint: 'e.g. 2.40',
              icon: Icons.swap_horiz,
              validator: _validateDouble,
              allowNegative: true,
            ),
            const SizedBox(height: 24),
            _buildSectionLabel(context, 'Orientation (degrees, which way the marker faces)'),
            const SizedBox(height: 12),
            _CoordField(
              controller: _rollCtrl,
              label: 'Roll',
              hint: 'e.g. 0',
              icon: Icons.screen_rotation_outlined,
              validator: _validateDouble,
              allowNegative: true,
            ),
            const SizedBox(height: 12),
            _CoordField(
              controller: _pitchCtrl,
              label: 'Pitch',
              hint: 'e.g. 0',
              icon: Icons.sync_alt,
              validator: _validateDouble,
              allowNegative: true,
            ),
            const SizedBox(height: 12),
            _CoordField(
              controller: _yawCtrl,
              label: 'Yaw',
              hint: 'e.g. 0',
              icon: Icons.explore_outlined,
              validator: _validateDouble,
              allowNegative: true,
            ),
            const SizedBox(height: 32),
            FilledButton.icon(
              onPressed: _save,
              icon: const Icon(Icons.save),
              label: Text(_isEditing ? 'Update Marker' : 'Add Marker'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionLabel(BuildContext context, String text) {
    return Text(
      text,
      style: Theme.of(context).textTheme.labelLarge?.copyWith(
            color: Theme.of(context).colorScheme.primary,
          ),
    );
  }
}

class _CoordField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  final IconData icon;
  final String? Function(String?)? validator;
  final bool readOnly;
  final List<TextInputFormatter>? inputFormatters;
  final TextInputType keyboardType;
  final bool allowNegative;

  const _CoordField({
    required this.controller,
    required this.label,
    required this.hint,
    required this.icon,
    this.validator,
    this.readOnly = false,
    this.inputFormatters,
    this.keyboardType = const TextInputType.numberWithOptions(decimal: true, signed: true),
    this.allowNegative = false,
  });

  void _toggleSign() {
    final text = controller.text.trim();
    if (text.startsWith('-')) {
      controller.text = text.substring(1);
    } else {
      controller.text = '-$text';
    }
    controller.selection = TextSelection.collapsed(offset: controller.text.length);
  }

  @override
  Widget build(BuildContext context) {
    // Many Android keyboards hide the "-" key for numeric inputs regardless
    // of the `signed` flag, so negative values need an explicit toggle
    // rather than relying on the OS keyboard to offer one.
    return TextFormField(
      controller: controller,
      readOnly: readOnly,
      keyboardType: keyboardType,
      inputFormatters: inputFormatters ??
          (allowNegative
              ? [FilteringTextInputFormatter.allow(RegExp(r'[0-9.\-]'))]
              : null),
      validator: validator,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        prefixIcon: Icon(icon),
        suffixIcon: allowNegative && !readOnly
            ? IconButton(
                tooltip: 'Toggle +/-',
                icon: const Text('+/-', style: TextStyle(fontWeight: FontWeight.bold)),
                onPressed: _toggleSign,
              )
            : null,
        border: const OutlineInputBorder(),
        filled: readOnly,
      ),
    );
  }
}
