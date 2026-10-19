import re
import chardet
import urllib.parse
from pathlib import Path
from typing import List, Optional, Set, Dict, Tuple
import pglast
from pglast import parse_sql
from pglast.ast import InsertStmt, SelectStmt, WithClause, ResTarget, String, RangeVar, JoinExpr, ColumnRef, Alias

from models import Finding, Severity
from config import get_config


class ReviewEngine:
    def __init__(self):
        self.config = get_config()
        self.sr_prefixes_pattern = re.compile(
            r"(?<![A-Za-z0-9])(?:" + "|".join(self.config.sr_prefixes) + r")\d{9}(?!\d)"
        )
        self.embedded_sql_pattern = re.compile(r"%[0-9A-Fa-f]{2}")
        self.template_fragment_pattern = re.compile(r"\$\{.*?\}")
        self.smart_quote_pattern = re.compile(r"[\u2018\u2019\u201C\u201D\u2013\u2014\u2026]")
        self.invisible_char_pattern = re.compile(r"[\u200B\u200C\u200D\uFEFF]")

    def review_file(self, sql_path: str) -> List[Finding]:
        findings = []
        content, encoding_warning = self._read_file_with_encoding(sql_path)
        if encoding_warning:
            findings.append(encoding_warning)

        smart_quote_findings = self._check_smart_quotes(content, sql_path)
        findings.extend(smart_quote_findings)

        syntax_findings = self._check_postgresql_syntax(content, sql_path)
        findings.extend(syntax_findings)

        locale_findings = self._check_message_locale(content, sql_path)
        findings.extend(locale_findings)

        embedded_findings = self._check_embedded_sql(content, sql_path)
        findings.extend(embedded_findings)

        if not findings:
            findings.append(Finding(
                severity="info",
                file=Path(sql_path).name,
                line=0,
                title="No issues found",
                description="All checks passed.",
                recommendation="No action required.",
            ))

        return findings

    def _read_file_with_encoding(self, sql_path: str) -> tuple[str, Optional[Finding]]:
        with open(sql_path, "rb") as f:
            raw = f.read()

        result = chardet.detect(raw)
        encoding = result.get("encoding", "utf-8")
        confidence = result.get("confidence", 0)

        if encoding and encoding.lower() != "utf-8" and confidence > 0.7:
            try:
                content = raw.decode(encoding)
                warning = Finding(
                    severity="warning",
                    file=Path(sql_path).name,
                    line=0,
                    title="Non-UTF-8 encoding detected",
                    description=f"File appears to be encoded in {encoding} (confidence: {confidence:.0%}). This may cause character corruption.",
                    recommendation="Save the file as UTF-8 before execution.",
                )
                return content, warning
            except UnicodeDecodeError:
                pass

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("utf-8", errors="replace")
            warning = Finding(
                severity="warning",
                file=Path(sql_path).name,
                line=0,
                title="Encoding detection failed",
                description="Could not reliably detect file encoding. File read with replacement characters.",
                recommendation="Verify file encoding and save as UTF-8.",
            )
            return content, warning

        return content, None

    def _check_smart_quotes(self, content: str, sql_path: str) -> List[Finding]:
        findings = []
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            if self.smart_quote_pattern.search(line) or self.invisible_char_pattern.search(line):
                findings.append(Finding(
                    severity="warning",
                    file=Path(sql_path).name,
                    line=i,
                    title="Typographic or invisible characters detected",
                    description=f"Line contains smart quotes or invisible Unicode characters: {repr(line[:100])}",
                    recommendation="Replace typographic quotes ('\"') with straight quotes ('\") and remove invisible characters.",
                ))
        return findings

    def _check_postgresql_syntax(self, content: str, sql_path: str) -> List[Finding]:
        findings = []
        statements = self._split_statements(content)

        for stmt_text, start_line in statements:
            try:
                parse_sql(stmt_text)
            except Exception as e:
                findings.append(Finding(
                    severity="error",
                    file=Path(sql_path).name,
                    line=start_line,
                    title="PostgreSQL syntax error",
                    description=str(e),
                    recommendation="Fix the syntax error according to PostgreSQL documentation.",
                ))

        return findings

    def _split_statements(self, content: str) -> List[tuple[str, int]]:
        statements = []
        lines = content.splitlines()
        current_stmt = []
        current_stmt_start = 1

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            if not stripped or stripped.startswith("--"):
                if not current_stmt:
                    current_stmt_start = i + 1
                continue
            
            if not current_stmt:
                current_stmt_start = i
            
            current_stmt.append(line)
            stmt_text = "\n".join(current_stmt).strip()
            
            if stmt_text.endswith(";"):
                statements.append((stmt_text, current_stmt_start))
                current_stmt = []

        if current_stmt:
            stmt_text = "\n".join(current_stmt).strip()
            if stmt_text:
                statements.append((stmt_text, current_stmt_start))

        return statements

    def _check_message_locale(self, content: str, sql_path: str) -> List[Finding]:
        findings = []
        statements = self._split_statements(content)

        key_locales: Dict[str, Set[str]] = {}
        key_first_line: Dict[str, int] = {}
        missing_locale_col_keys: List[Tuple[str, int]] = []
        complex_insert_keys: List[Tuple[str, int]] = []

        for stmt_text, start_line in statements:
            try:
                parsed = parse_sql(stmt_text)
                for node in parsed:
                    if isinstance(node.stmt, InsertStmt):
                        insert = node.stmt
                        if self._is_ims_message_insert(insert):
                            self._collect_locale_info(insert, stmt_text, start_line,
                                                     key_locales, key_first_line,
                                                     missing_locale_col_keys, complex_insert_keys)
            except Exception:
                pass

        for key, line in missing_locale_col_keys:
            findings.append(Finding(
                severity="error",
                file=Path(sql_path).name,
                line=line,
                title="Missing message_locale column",
                description=f"INSERT into ims_message for message_key '{key}' has no message_locale column.",
                recommendation="Add message_locale column to the INSERT statement.",
            ))

        for key, line in complex_insert_keys:
            if key == "multiple (INSERT ... SELECT)":
                findings.append(Finding(
                    severity="warning",
                    file=Path(sql_path).name,
                    line=line,
                    title="Complex INSERT into ims_message requires manual check",
                    description="INSERT ... SELECT or ON CONFLICT detected. Cannot automatically verify message_locale values.",
                    recommendation="Manually verify that all message_key values have corresponding en_US rows.",
                ))
            else:
                findings.append(Finding(
                    severity="warning",
                    file=Path(sql_path).name,
                    line=line,
                    title="Complex INSERT into ims_message requires manual check",
                    description=f"INSERT ... SELECT or ON CONFLICT for message_key '{key}'. Cannot automatically verify message_locale values.",
                    recommendation="Manually verify that all message_key values have corresponding en_US rows.",
                ))

        for key, locales in key_locales.items():
            if self.config.required_locale not in locales:
                line = key_first_line.get(key, 0)
                findings.append(Finding(
                    severity="error",
                    file=Path(sql_path).name,
                    line=line,
                    title=f"Missing message_locale {self.config.required_locale}",
                    description=f"message_key '{key}' has only {', '.join(sorted(locales))}.",
                    recommendation=f"Add an INSERT for {key} with message_locale = '{self.config.required_locale}'.",
                ))

        return findings

    def _collect_locale_info(self, insert: InsertStmt, stmt_text: str, start_line: int,
                            key_locales: Dict[str, Set[str]], key_first_line: Dict[str, int],
                            missing_locale_col_keys: List[Tuple[str, int]],
                            complex_insert_keys: List[Tuple[str, int]]):
        cols = [col.name.lower() for col in insert.cols] if insert.cols else []

        if "message_key" not in cols:
            return

        key_idx = cols.index("message_key")

        has_locale_col = "message_locale" in cols
        locale_idx = cols.index("message_locale") if has_locale_col else -1

        is_values = hasattr(insert, "selectStmt") and insert.selectStmt is not None and getattr(insert.selectStmt, "valuesLists", None) is not None

        if not is_values:
            complex_insert_keys.append(("multiple (INSERT ... SELECT)", start_line))
            return

        if not has_locale_col:
            for values_list in insert.selectStmt.valuesLists:
                if key_idx < len(values_list):
                    key_val = self._get_string_value(values_list[key_idx])
                    if key_val:
                        missing_locale_col_keys.append((key_val, start_line))
            return

        for values_list in insert.selectStmt.valuesLists:
            if key_idx < len(values_list) and locale_idx < len(values_list):
                key_val = self._get_string_value(values_list[key_idx])
                locale_val = self._get_string_value(values_list[locale_idx])
                if key_val and locale_val:
                    if key_val not in key_locales:
                        key_locales[key_val] = set()
                        key_first_line[key_val] = start_line
                    key_locales[key_val].add(locale_val)

    def _extract_key_from_values(self, insert: InsertStmt, key_idx: int) -> Optional[str]:
        if not hasattr(insert, "selectStmt") or not insert.selectStmt:
            return None
        for values_list in insert.selectStmt.valuesLists:
            if key_idx < len(values_list):
                return self._get_string_value(values_list[key_idx])
        return None

    def _extract_key_from_complex_insert(self, insert: InsertStmt, key_idx: int) -> Optional[str]:
        return None

    def _get_string_value(self, node) -> Optional[str]:
        if hasattr(node, "val") and hasattr(node.val, "sval"):
            return node.val.sval
        return None

    def _is_ims_message_insert(self, insert: InsertStmt) -> bool:
        if not insert.relation or not hasattr(insert.relation, "relname"):
            return False
        table_name = insert.relation.relname.lower()
        return table_name == self.config.message_table.lower()

    def _check_embedded_sql(self, content: str, sql_path: str) -> List[Finding]:
        findings = []
        statements = self._split_statements(content)

        for stmt_text, start_line in statements:
            try:
                parsed = parse_sql(stmt_text)
                for node in parsed:
                    if isinstance(node.stmt, InsertStmt):
                        self._extract_embedded_sql_from_insert(node.stmt, stmt_text, start_line, sql_path, findings)
            except Exception:
                pass

        return findings

    def _extract_embedded_sql_from_insert(self, insert: InsertStmt, stmt_text: str, start_line: int, sql_path: str, findings: List[Finding]):
        if not hasattr(insert, "selectStmt") or insert.selectStmt is None:
            return

        if not self._is_embedded_sql_target_table(insert):
            return

        cols = [col.name.lower() for col in insert.cols] if insert.cols else []
        select_stmt = insert.selectStmt

        if not select_stmt or not hasattr(select_stmt, "valuesLists") or not select_stmt.valuesLists:
            return

        for target_list in select_stmt.valuesLists:
            for i, val in enumerate(target_list):
                if i >= len(cols):
                    continue
                col_name = cols[i]
                if col_name in ("table_name", "query_sql", "where_clause", "sql_text"):
                    self._check_embedded_value(val, col_name, stmt_text, start_line, sql_path, findings)

    def _is_embedded_sql_target_table(self, insert: InsertStmt) -> bool:
        if not insert.relation or not hasattr(insert.relation, "relname"):
            return False
        table_name = insert.relation.relname.lower()
        return table_name in ("ims_autocomplete_config", "ims_report_config", "ims_dynamic_sql")

    def _check_embedded_value(self, val, col_name: str, stmt_text: str, start_line: int, sql_path: str, findings: List[Finding]):
        if not hasattr(val, "val") or not hasattr(val.val, "sval"):
            return

        text = val.val.sval
        if not text or not self.embedded_sql_pattern.search(text):
            return

        try:
            decoded = urllib.parse.unquote(text)
        except Exception:
            return

        if not decoded.strip().lower().startswith(("select", "with")):
            return

        cleaned = self.template_fragment_pattern.sub("NULL", decoded)

        try:
            parsed = parse_sql(cleaned)
            for node in parsed:
                self._validate_embedded_query(node.stmt, col_name, start_line, sql_path, findings)
        except Exception as e:
            findings.append(Finding(
                severity="error",
                file=Path(sql_path).name,
                line=start_line,
                title="Embedded SQL parse error",
                description=f"Failed to parse embedded SQL in column {col_name}: {e}",
                recommendation="Fix the embedded SQL syntax.",
            ))

    def _validate_embedded_query(self, stmt, col_name: str, start_line: int, sql_path: str, findings: List[Finding]):
        if isinstance(stmt, SelectStmt):
            self._check_select_aliases(stmt, col_name, start_line, sql_path, findings)
        elif isinstance(stmt, WithClause):
            for cte in stmt.ctes:
                if hasattr(cte, "ctequery") and isinstance(cte.ctequery, SelectStmt):
                    self._check_select_aliases(cte.ctequery, col_name, start_line, sql_path, findings)

    def _check_select_aliases(self, select: SelectStmt, col_name: str, start_line: int, sql_path: str, findings: List[Finding]):
        aliases = self._collect_aliases(select)

        for target in select.targetList:
            if isinstance(target, ResTarget) and target.val:
                self._check_column_ref(target.val, aliases, col_name, start_line, sql_path, findings)

        if hasattr(select, "whereClause") and select.whereClause:
            self._check_column_ref(select.whereClause, aliases, col_name, start_line, sql_path, findings)

        if hasattr(select, "fromClause") and select.fromClause:
            for item in select.fromClause:
                if isinstance(item, JoinExpr):
                    self._check_join_aliases(item, aliases, col_name, start_line, sql_path, findings)

    def _check_column_ref(self, node, aliases: Set[str], col_name: str, start_line: int, sql_path: str, findings: List[Finding]):
        if isinstance(node, ColumnRef):
            parts = []
            for field in node.fields:
                if hasattr(field, "sval"):
                    parts.append(field.sval)
                elif hasattr(field, "name"):
                    parts.append(field.name)
            if len(parts) > 2:
                findings.append(Finding(
                    severity="error",
                    file=Path(sql_path).name,
                    line=start_line,
                    title="Invalid column reference in embedded SQL",
                    description=f"Column reference has {len(parts)} parts: {'.'.join(parts)} (likely a typo)",
                    recommendation="Fix the column reference to use at most two qualifiers (table.column).",
                ))
            elif len(parts) == 2:
                qualifier = parts[0]
                if qualifier not in aliases:
                    findings.append(Finding(
                        severity="error",
                        file=Path(sql_path).name,
                        line=start_line,
                        title="Undefined table alias in embedded SQL",
                        description=f"Column qualifier '{qualifier}' is not a defined table alias (defined: {', '.join(sorted(aliases)) or 'none'})",
                        recommendation="Ensure all table aliases are properly defined in the query.",
                    ))
        elif hasattr(node, "args"):
            for arg in node.args:
                self._check_column_ref(arg, aliases, col_name, start_line, sql_path, findings)
        elif hasattr(node, "larg") and hasattr(node, "rarg"):
            self._check_column_ref(node.larg, aliases, col_name, start_line, sql_path, findings)
            self._check_column_ref(node.rarg, aliases, col_name, start_line, sql_path, findings)

    def _check_join_aliases(self, join: JoinExpr, aliases: Set[str], col_name: str, start_line: int, sql_path: str, findings: List[Finding]):
        if hasattr(join, "larg"):
            self._check_join_aliases(join.larg, aliases, col_name, start_line, sql_path, findings)
        if hasattr(join, "rarg"):
            self._check_join_aliases(join.rarg, aliases, col_name, start_line, sql_path, findings)
        if hasattr(join, "quals"):
            self._check_column_ref(join.quals, aliases, col_name, start_line, sql_path, findings)

    def _collect_aliases(self, select: SelectStmt) -> Set[str]:
        aliases = set()
        if hasattr(select, "fromClause") and select.fromClause:
            for item in select.fromClause:
                if isinstance(item, RangeVar) and item.alias and hasattr(item.alias, "aliasname"):
                    aliases.add(item.alias.aliasname)
                elif hasattr(item, "alias") and item.alias and hasattr(item.alias, "aliasname"):
                    aliases.add(item.alias.aliasname)
        return aliases


def review_sql_file(sql_path: str) -> List[Finding]:
    engine = ReviewEngine()
    return engine.review_file(sql_path)