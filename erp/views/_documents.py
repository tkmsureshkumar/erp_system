"""
erp/views/_documents.py
Reusable document-attachment panel.
Drop into any module: render_document_panel(sb, record_type, record_id).

Supports:
  • Multiple file uploads in one go
  • PDF merge: combine 2+ PDFs into a single file before uploading
    (useful for 30 daily logsheets → one combined PDF)
  • Inline document viewer (PDF embedded, images displayed, Word opened in browser)
"""
from __future__ import annotations

import io

import streamlit as st
import streamlit.components.v1 as components

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
.doc-merge-hint {
    font-size: 11px; color: #6B7280;
    background: #FFF7ED; border: 1px solid #FED7AA;
    border-radius: 6px; padding: 7px 11px; margin-top: 6px;
}
</style>
"""

_CSS_INJECTED: set[str] = set()


def _inject_css(key: str = "doc_css") -> None:
    if key not in _CSS_INJECTED:
        st.markdown(_CSS, unsafe_allow_html=True)
        _CSS_INJECTED.add(key)


def _merge_pdfs(files) -> bytes:
    """Merge a list of UploadedFile PDF objects into a single PDF bytes object."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        raise RuntimeError(
            "pypdf is not installed. Run: pip install pypdf>=4.0"
        )

    writer = PdfWriter()
    for f in files:
        raw = f.read()
        reader = PdfReader(io.BytesIO(raw))
        for page in reader.pages:
            writer.add_page(page)
        f.seek(0)  # reset so callers can re-read if needed

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ── Inline document viewer dialog ─────────────────────────────────────────────

@st.dialog("Document Preview", width="large")
def _doc_preview_dialog() -> None:
    info = st.session_state.get("_doc_preview_info", {})
    signed_url: str = info.get("url", "")
    fname: str      = info.get("fname", "Document")
    ftype: str      = info.get("ftype", "")

    if not signed_url:
        st.error("Preview URL is unavailable.")
        return

    st.markdown(
        f"<div style='font-size:13px;font-weight:600;color:#111827;"
        f"margin-bottom:12px;word-break:break-all;'>{fname}</div>",
        unsafe_allow_html=True,
    )

    if ftype == "image":
        st.image(signed_url, use_container_width=True)

    elif ftype == "pdf":
        # Embed PDF via iframe — works in all modern browsers
        components.html(
            f"""
            <iframe
              src="{signed_url}"
              width="100%"
              height="750"
              style="border:none;border-radius:6px;"
              title="{fname}">
              <p>Your browser does not support inline PDF viewing.
                 <a href="{signed_url}" target="_blank">Open PDF</a>
              </p>
            </iframe>
            """,
            height=760,
            scrolling=False,
        )

    else:
        # Word / unknown — can't embed natively; open in new tab
        st.info(
            "This file type cannot be previewed inline. "
            "Click the button below to open it in your browser.",
            icon="ℹ️",
        )

    st.link_button(
        "Open in new tab",
        signed_url,
        use_container_width=True,
    )


# ── Panel render ───────────────────────────────────────────────────────────────

def render_document_panel(
    sb,
    record_type: str,
    record_id: str | None,
    key_prefix: str = "",
    uploaded_by: str = "",
) -> None:
    """Render upload widget + document list for any record.

    Supports multiple file selection, optional PDF merge, and inline preview.
    """
    _inject_css()

    if not record_id:
        st.info("Save this record first to attach documents.", icon="ℹ️")
        return

    # ── Upload section ─────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div class='doc-sec-hdr'>"
            "<span class='msr' style='font-size:14px;color:#E87722;'>attach_file</span>"
            "Attach Documents</div>",
            unsafe_allow_html=True,
        )

        up_files = st.file_uploader(
            "Files",
            type=_ALLOWED_EXTENSIONS,
            accept_multiple_files=True,
            key=f"_doc_up_{key_prefix}_{record_id}",
            help="Select one or more files. PDFs can be merged before uploading.",
            label_visibility="collapsed",
        )

        # ── PDF merge option (shown only when 2+ PDFs are selected) ───────────
        _all_pdfs  = bool(up_files) and all(
            f.name.lower().endswith(".pdf") for f in up_files
        )
        _multi_pdf = _all_pdfs and len(up_files) >= 2

        do_merge    = False
        merged_name = "combined.pdf"

        if _multi_pdf:
            st.markdown(
                "<div class='doc-merge-hint'>"
                "📎 Multiple PDFs selected — you can combine them into one file "
                "(e.g. 30 daily logsheets → one combined PDF)."
                "</div>",
                unsafe_allow_html=True,
            )
            merge_col, name_col = st.columns([1, 2])
            with merge_col:
                do_merge = st.checkbox(
                    "Combine into one PDF",
                    value=True,
                    key=f"_doc_merge_{key_prefix}_{record_id}",
                )
            if do_merge:
                with name_col:
                    merged_name = st.text_input(
                        "Merged filename",
                        value="combined_logsheets.pdf",
                        key=f"_doc_mname_{key_prefix}_{record_id}",
                        label_visibility="collapsed",
                        placeholder="combined_logsheets.pdf",
                    )
                    if merged_name and not merged_name.lower().endswith(".pdf"):
                        merged_name += ".pdf"

        # ── Remarks + Attach button ────────────────────────────────────────────
        rem_col, btn_col = st.columns([5, 1])
        with rem_col:
            remarks = st.text_input(
                "Remarks",
                placeholder="Optional description…",
                key=f"_doc_rem_{key_prefix}_{record_id}",
                label_visibility="collapsed",
            )
        with btn_col:
            n_files  = len(up_files) if up_files else 0
            btn_label = (
                "Merge & Upload"  if (do_merge and _multi_pdf) else
                f"Upload {n_files}" if n_files > 1 else
                "Attach"
            )
            attach = st.button(
                btn_label,
                key=f"_doc_attach_{key_prefix}_{record_id}",
                use_container_width=True,
                type="primary",
                disabled=(n_files == 0),
            )

        # ── Handle upload ──────────────────────────────────────────────────────
        if attach and up_files:
            if do_merge and _multi_pdf:
                try:
                    merged_bytes = _merge_pdfs(up_files)
                    sb.upload_document(
                        record_type  = record_type,
                        record_id    = record_id,
                        file_bytes   = merged_bytes,
                        file_name    = merged_name or "combined.pdf",
                        file_size_kb = max(1, len(merged_bytes) // 1024),
                        remarks      = remarks.strip() or f"Merged from {len(up_files)} PDFs",
                        uploaded_by  = uploaded_by,
                    )
                    st.toast(
                        f"{len(up_files)} PDFs merged into '{merged_name}' and uploaded.",
                        icon="✅",
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Merge failed: {exc}")
            else:
                errors: list[str] = []
                for f in up_files:
                    try:
                        raw = f.read()
                        sb.upload_document(
                            record_type  = record_type,
                            record_id    = record_id,
                            file_bytes   = raw,
                            file_name    = f.name,
                            file_size_kb = max(1, len(raw) // 1024),
                            remarks      = remarks.strip(),
                            uploaded_by  = uploaded_by,
                        )
                    except Exception as exc:
                        errors.append(f"{f.name}: {exc}")

                if errors:
                    st.error("Some uploads failed:\n" + "\n".join(errors))
                else:
                    count = len(up_files)
                    st.toast(
                        f"{count} file{'s' if count > 1 else ''} uploaded.",
                        icon="✅",
                    )
                st.rerun()

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
    uploaded_at = (doc.get("uploaded_at") or "")[:10]
    spath   = doc.get("storage_path", "")

    icon  = _TYPE_ICON.get(ftype, "insert_drive_file")
    color = _TYPE_COLOR.get(ftype, "#9CA3AF")
    meta  = " · ".join(filter(None, [
        ftype.upper() if ftype else "",
        f"{size_kb} KB" if size_kb else "",
        uploaded_at,
    ]))

    # Fetch signed URL once — used for both View and Download
    signed: str = ""
    if spath:
        try:
            signed = sb.get_signed_url(spath) or ""
        except Exception:
            signed = ""

    info_col, act_col, del_col = st.columns([6, 3, 1])

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

    with act_col:
        if signed:
            v_col, d_col = st.columns(2)
            with v_col:
                if st.button(
                    "View",
                    key=f"_doc_view_{key_prefix}_{doc_id}",
                    use_container_width=True,
                    help="Preview document inside the app",
                ):
                    st.session_state["_doc_preview_info"] = {
                        "url":   signed,
                        "fname": fname,
                        "ftype": ftype,
                    }
                    _doc_preview_dialog()
            with d_col:
                st.link_button(
                    "Download",
                    signed,
                    use_container_width=True,
                )

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
