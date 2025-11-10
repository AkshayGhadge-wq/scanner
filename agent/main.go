// go:build linux
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"
)

type Config struct {
	API         string `json:"api"`
	SourceID    string `json:"source_id"`
	EnrollToken string `json:"enroll_token"`
}

type EnrollResp struct {
	AgentID      string `json:"agent_id"`
	PollURL      string `json:"poll_url"`
	HeartbeatURL string `json:"heartbeat_url"`
}

var httpc = &http.Client{ Timeout: 20 * time.Second }

func readConfig(path string) (*Config, error) {
	b, err := os.ReadFile(path)
	if err != nil { return nil, err }
	// allow yaml with simple keys (very naive)
	txt := string(b)
	cfg := &Config{}
	for _, line := range strings.Split(txt, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") { continue }
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 { continue }
		k := strings.TrimSpace(parts[0])
		v := strings.Trim(strings.TrimSpace(parts[1]), "'\"")
		switch k {
		case "api": cfg.API = v
		case "source_id": cfg.SourceID = v
		case "enroll_token": cfg.EnrollToken = v
		}
	}
	return cfg, nil
}

func postJSON(url string, body any, out any) error {
	b, _ := json.Marshal(body)
	req, _ := http.NewRequest("POST", url, bytes.NewReader(b))
	req.Header.Set("Content-Type","application/json")
	resp, err := httpc.Do(req)
	if err != nil { return err }
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		x, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(x))
	}
	if out != nil { return json.NewDecoder(resp.Body).Decode(out) }
	return nil
}

func getJSON(url string, out any) error {
	resp, err := httpc.Get(url)
	if err != nil { return err }
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		x, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(x))
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func run(cmd string, args ...string) string {
	c := exec.Command(cmd, args...)
	b, err := c.CombinedOutput()
	if err != nil { return strings.TrimSpace(string(b)) }
	return strings.TrimSpace(string(b))
}

func collectSummary() map[string]any {
	return map[string]any{
		"hostname": run("hostname"),
		"kernel": run("uname","-r"),
	}
}

func collectPackages() map[string]any {
	out := ""
	if _, err := exec.LookPath("dpkg"); err == nil {
		out = run("bash","-lc","dpkg -l | head -n 200")
	} else if _, err := exec.LookPath("rpm"); err == nil {
		out = run("bash","-lc","rpm -qa | head -n 200")
	}
	return map[string]any{"sample": out}
}

func collectServices() map[string]any {
	return map[string]any{"systemd": run("bash","-lc","systemctl list-units --type=service --no-pager | head -n 200")}
}

func collectPorts() map[string]any {
	return map[string]any{"tcp": run("bash","-lc","ss -lntp || netstat -lntp | head -n 200")}
}

func collectRuntimes() map[string]any {
	return map[string]any{
		"node": run("node","-v"),
		"java": run("bash","-lc","java -version 2>&1 | head -n 1"),
		"python": run("python3","-V"),
		"php": run("php","-v"),
	}
}

func main(){
	confPath := flag.String("config","/etc/youragent/config.yaml","config file")
	flag.Parse()
	cfg, err := readConfig(*confPath)
	if err != nil { fmt.Println("config:", err); os.Exit(1) }
	// enroll
	enr := &EnrollResp{}
	err = postJSON(cfg.API+"/agent/enroll", map[string]any{"source_id": cfg.SourceID, "enroll_token": cfg.EnrollToken, "version": "0.1.0"}, enr)
	if err != nil { fmt.Println("enroll:", err); os.Exit(1) }
	agentID := enr.AgentID
	// heartbeat loop + job poll
	for {
		// heartbeat
		_ = postJSON(cfg.API+"/agent/heartbeat", map[string]any{
			"agent_id": agentID, "caps": map[string]any{"linux": true, "docker": (run("which","docker")!="")},
			"summary": collectSummary(),
		}, nil)

		// poll job
		var nxt struct{ Job *struct{ JobID string `json:"job_id"`; Kind string `json:"kind"` } `json:"job"` }
		_ = getJSON(cfg.API+"/agent/jobs/next?agent_id="+agentID, &nxt)
		if nxt.Job != nil {
			jobID := nxt.Job.JobID
			switch nxt.Job.Kind {
			case "host_inventory":
				_ = postJSON(cfg.API+"/agent/jobs/"+jobID+"/chunk", map[string]any{"data_type":"packages","payload":collectPackages()}, nil)
				_ = postJSON(cfg.API+"/agent/jobs/"+jobID+"/chunk", map[string]any{"data_type":"services","payload":collectServices()}, nil)
				_ = postJSON(cfg.API+"/agent/jobs/"+jobID+"/chunk", map[string]any{"data_type":"ports","payload":collectPorts()}, nil)
				_ = postJSON(cfg.API+"/agent/jobs/"+jobID+"/chunk", map[string]any{"data_type":"runtimes","payload":collectRuntimes()}, nil)
			default:
				_ = postJSON(cfg.API+"/agent/jobs/"+jobID+"/chunk", map[string]any{"data_type":"info","payload":map[string]any{"msg":"unknown job kind"}}, nil)
			}
			_ = postJSON(cfg.API+"/agent/jobs/"+jobID+"/done", true, nil)
		}
		time.Sleep(8 * time.Second)
	}
}