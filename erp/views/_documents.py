"""
erp/views/_documents.py
Reusable document-attachment panel.
Drop into any module: render_document_panel(sb, record_type, record_id).
"""
from __future__ import annotations

import streamlit as st

_ALLOWED_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "webp", "doc", "docx"]

_TYPE_ICON = {
    "pdf":   "picture_as_pdf",
    "image": "image",
    "word":  "description",
}
_TYPE_COLOR = {
    "pdf":   "#EF4444",
    "image": "#10B981",
    "word":  "#2563EB",
}

_CSS = """
<style>
.doc-sec-hdr {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #E87722;
    margin-bottom: 10px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}
.doc-row-wrap {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 0; border-bottom: 1px solid #F1F5F9;
}
.doc-row-wrap:last-child { border-bottom: none; }
.doc-fname  { font-size: 13px; font-weight: 600; color: #111827; }
.doc-meta   { font-size: 11px; color: #6B7280; margin-top: 2px; }
.doc-remark { font-size: 11px; color: #9CA3AF; font-style: italic; }
.doc-empty  {
    text-align: center; padding: 22px 0;
    color: #9CA3AF; font-size: 12px;
}
</style>
"""

_CSS_INJECTED: set[str] = set()


def _inject_css(key: str = "doc_css") -> None:
    if key not in _CSS_INJECTED:
        st.markdown(_CSS, unsafe_allow_html=True)
        _CSS_INJECTED.add(key)


def render_document_panel(
    sb,
    record_type: str,
    record_id: str | None,
    key_prefix: str = "",
    uploaded_by: str = "",
) -> None:
    """Render upload widget + document list for any record."""
    _inject_css()

    if not record_id:
        st.info("Save this record first to attach documents.", icon="ℹ️")
        return

    # ── Upload ─────────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div class='doc-sec-hdr'>"
            "<span class='msr' style='font-size:14px;color:#E87722;'>attach_file</span>"
            "Attach Document</div>",
            unsafe_allow_html=True,
        )
        up_file = st.file_uploader(
            "File",
            type=_ALLOWED_EXTENSIONS,
            key=f"_doc_up_{key_prefix}_{record_id}",
            help="Accepted: PDF · Images (JPG, PNG, WebP) · Word (DOC, DOCX)",
            label_visibility="collapsed",
        )
        rem_col, btn_col = st.columns([5, 1])
        with rem_col:
            remarks = st.text_input(
                "Remarks",
                placeholder="Optional description…",
                key=f"_doc_rem_{key_prefix}_{record_id}",
                label_visibility="collapsed",
            )
        with btn_col:
            attach = st.button(
                "Attach",
                key=f"_doc_attach_{key_prefix}_{record_id}",
                use_container_width=True,
                type="primary",
                disabled=(up_file is None),
            )

        if attach and up_file:
            try:
                raw   = up_file.read()
                sb.upload_document(
                    record_type  = record_type,
                    record_id    = record_id,
                    file_bytes   = raw,
                    file_name    = up_file.name,
                    file_size_kb = max(1, len(raw) // 1024),
                    remarks      = remarks.strip(),
                    uploaded_by  = uploaded_by,
                )
                st.toast(f"'{up_file.name}' attached.", icon="✅")
                st.rerun()
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

    # ── Document list ──────────────────────────────────────────────────────────
    try:
        docs = sb.list_documents(record_type, record_id)
    except Exception as exc:
        st.warning(f"Could not load documents: {exc}")
        return

    if not docs:
        st.markdown(
            "<div class='doc-empty'>No documents attached yet.</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"<div style='font-size:11px;color:#6B7280;margin:10px 0 4px;'>"
        f"{len(docs)} document{'s' if len(docs) != 1 else ''} attached</div>",
        unsafe_allow_html=True,
    )

    for doc in docs:
        _render_row(sb, doc, key_prefix)


def _render_row(sb, doc: dict, key_prefix: str) -> None:
    doc_id  = doc.get("id", "")
    fname   = doc.get("file_name", "Unknown")
    ftype   = doc.get("file_type", "")
    size_kb = doc.get("file_size_kb") or 0
    remarks = doc.get("remarks") or ""
    date    = (doc.get("uploaded_at") or "")[:10]
    spath   = doc.get("storage_path", "")

    icon  = _TYPE_ICON.get(ftype, "insert_drive_file")
    color = _TYPE_COLOR.get(ftype, "#9CA3AF")
    meta  = " · ".join(filter(None, [
        ftype.upper() if ftype else "",
        f"{size_kb} KB" if size_kb else "",
        date,
    ]))

    info_col, dl_col, del_col = st.columns([6, 2, 1])

    with info_col:
        st.markdown(
            f"<div class='doc-row-wrap'>"
            f"<span class='msr' style='font-size:22px;color:{color};flex-shrink:0;'>"
            f"{icon}</span>"
            f"<div>"
            f"<div class='doc-fname'>{fname}</div>"
            f"<div class='doc-meta'>{meta}</div>"
            f"{'<div class=\"doc-remark\">' + remarks + '</div>' if remarks else ''}"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    with dl_col:
        if spath:
            try:
                signed = sb.get_signed_url(spath)
                if signed:
                    st.link_button("Download", signed, use_container_width=True)
            except Exception:
                st.caption("URL unavailable")

    with del_col:
        if st.button(
            "🗑", key=f"_doc_del_{key_prefix}_{doc_id}",
            help="Delete document",
        ):
            try:
                sb.delete_document(doc_id, spath)
                st.toast(f"'{fname}' deleted.", icon="🗑️")
                st.rerun()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")
