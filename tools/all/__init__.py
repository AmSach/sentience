"""All tools - 100+ tools by category."""
TOOL_CATEGORIES = {
    "filesystem": ["read_file","write_file","glob","grep","edit_file","delete_file","rename_file","copy_file","move_file","mkdir","list_dir","file_info","chmod","zip_folder","unzip_file"],
    "code": ["run_code","write_code","read_code","debug_code","git_commit","git_push","git_pull","git_branch","run_test","lint_code","format_code","deploy","docker_build","docker_run"],
    "web": ["fetch_url","post_json","http_request","scrape_page","parse_html","extract_links","web_search"],
    "data": ["query_sql","read_csv","write_csv","read_json","write_json","filter_data","visualize","export"],
    "email": ["gmail_send","gmail_list","gmail_search","gmail_read","gmail_reply","smtp_send","outlook_send"],
    "calendar": ["cal_list","cal_event","cal_update","cal_delete","cal_search","cal_invite"],
    "social": ["twitter_tweet","twitter_search","linkedin_post","instagram_post","discord_send","slack_post","telegram_send"],
    "cloud": ["s3_upload","s3_download","s3_list","gcs_upload","gcs_download","dropbox_upload","dropbox_download","gdrive_upload","gdrive_download","onedrive_upload"],
    "remote": ["ssh_connect","ssh_run","ssh_upload","ssh_download","scp","ping","port_scan","dns_lookup","vnc_connect"],
    "media": ["image_resize","image_crop","image_filter","pdf_split","pdf_merge","video_cut","video_merge","audio_transcribe","screenshot"],
    "security": ["hash_file","encrypt_file","decrypt_file","gen_password","scan_port","check_ssl","audit_perms"],
    "system": ["run_shell","check_process","kill_process","cpu_usage","mem_usage","disk_usage","netstat","log_tail","cron_list","cron_create","service_restart"]
}
def get_tools_by_category(cat): return TOOL_CATEGORIES.get(cat,[])
def get_all_tools(): return [t for c in TOOL_CATEGORIES.values() for t in c]
__all__ = ["TOOL_CATEGORIES","get_tools_by_category","get_all_tools"]
