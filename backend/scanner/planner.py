from typing import Dict, Any

def plan_resources(scan: Dict[str, Any]) -> Dict[str, Any]:
    http = scan.get("http", {})
    fp = scan.get("fingerprint", {})
    headers = http.get("headers", {})
    frameworks = set(fp.get("frameworks", [])) if isinstance(fp, dict) else set()
    site_is_spa = ("text/html" in (http.get("content_type","").lower()) and "Next.js" not in frameworks)
    cdn_hint = "via" in {k.lower(): v for k,v in headers.items()}

    if site_is_spa and "Express" not in frameworks:
        selected = "aws_static_spa"
        bom = ["S3 (private) + OAC", "CloudFront (HTTP/2/3)", "ACM cert (us-east-1)", "Route53", "CF Function headers"]
        files = {
            "main.tf": "// (see previous message version; keep short in agent demo)",
            "cf_headers.js": "function handler(e){var r=e.response,h=r.headers;function s(n,v){h[n.toLowerCase()]=[{key:n,value:v}]};s('X-Frame-Options','DENY');s('Permissions-Policy','camera=(), microphone=(), geolocation=()');s('Cross-Origin-Opener-Policy','same-origin');s('Cross-Origin-Resource-Policy','same-origin');return r;}"
        }
        cmds = ["terraform init","terraform apply -auto-approve","aws s3 sync dist/ s3://<bucket> --delete"]
    else:
        selected = "gcp_cloud_run_container"
        bom = ["Artifact Registry","Cloud Run","HTTPS LB + Cloud CDN","Secret Manager","Logging"]
        files = {"Dockerfile":"FROM nginx:alpine\nCOPY dist/ /usr/share/nginx/html"}
        cmds = ["gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/REPO/web:prod .",
                "gcloud run deploy web --image REGION-docker.pkg.dev/PROJECT/REPO/web:prod --region=REGION"]
    return {
        "selected_plan": selected,
        "bill_of_materials": bom,
        "provisioning": {"files": files, "commands": cmds}
    }