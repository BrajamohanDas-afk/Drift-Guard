from app.services.drift.rules.base import (
    BaseDriftRule,
    DriftAlertDraft,
    DriftRuleContext,
)


class CommandDeprecatedRule(BaseDriftRule):
    rule_type = "command_deprecated"
    severity = "medium"
    _BOUNDARY_CHARS = {" ", "\t", "\r", "\n", ";", "&", "|"}

    def _build_deprecation_map(self, context: DriftRuleContext) -> dict[str, dict]:
        raw = context.evidence.get("command_deprecations")
        if isinstance(raw, dict):
            normalized: dict[str, dict] = {}
            for command, metadata in raw.items():
                normalized_command = str(command).strip()
                if not normalized_command:
                    continue
                if not isinstance(metadata, dict) or not metadata:
                    continue
                normalized[normalized_command] = metadata
            return normalized
        return {}

    def _is_prefix_match(self, command: str, deprecated_command: str) -> bool:
        if command == deprecated_command:
            return True
        if not command.startswith(deprecated_command):
            return False
        if len(command) == len(deprecated_command):
            return True
        return command[len(deprecated_command)] in self._BOUNDARY_CHARS

    def _find_prefix_match(
        self, command: str, deprecation_map: dict[str, dict]
    ) -> dict | None:
        candidates = [
            (deprecated_command, metadata)
            for deprecated_command, metadata in deprecation_map.items()
            if self._is_prefix_match(command, deprecated_command)
        ]
        if not candidates:
            return None
        # Prefer the longest matching prefix for deterministic, specific matches.
        candidates.sort(key=lambda item: len(item[0]), reverse=True)
        return candidates[0][1]

    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        command_values = [
            str(entity.get("value", "")).strip()
            for entity in context.entities
            if str(entity.get("entity_type", "")).strip().lower() == "command"
            and str(entity.get("value", "")).strip()
        ]
        if not command_values:
            return []

        deprecation_map = self._build_deprecation_map(context)
        if not deprecation_map:
            return []

        alerts: list[DriftAlertDraft] = []
        for command in command_values:
            metadata = deprecation_map.get(command)
            if metadata is None:
                # Prefix match lets evidence deprecate command families.
                metadata = self._find_prefix_match(command, deprecation_map)
            if metadata is None:
                continue

            replacement = metadata.get("replacement")
            reason = metadata.get("reason")
            alerts.append(
                DriftAlertDraft(
                    rule_type=self.rule_type,
                    severity=self.severity,
                    message=f"Deprecated command found: {command}",
                    document_id=context.document_id,
                    evidence={
                        "command": command,
                        "replacement": replacement,
                        "reason": reason,
                    },
                )
            )

        return alerts
