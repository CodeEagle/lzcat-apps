package containerd

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"github.com/memohai/memoh/internal/config"
)

// LocalService is a minimal, file-backed "container" runner that launches
// the bridge binary as a local subprocess for each bot. It implements the
// containerd.Service interface partially — enough for workspace.Manager to
// manage workspaces without an embedded containerd.
type LocalService struct {
	logger    *slog.Logger
	dataRoot  string
	runtime   string
	binary    string
	mu        sync.Mutex
	procs     map[string]*os.Process // containerID -> process
	containersDir string
}

func NewLocalService(log *slog.Logger, cfg config.Config) (*LocalService, error) {
	dataRoot := cfg.Workspace.DataRoot
	if dataRoot == "" {
		dataRoot = config.DefaultDataRoot
	}
	runtime := cfg.Workspace.RuntimePath()
	binary := cfg.Containerd.Socktainer.BinaryPath
	// binary may be empty; caller should ensure bridge binary is available

	s := &LocalService{
		logger:    log.With(slog.String("service", "local-runner")),
		dataRoot:  dataRoot,
		runtime:   runtime,
		binary:    binary,
		procs:     make(map[string]*os.Process),
		containersDir: filepath.Join(dataRoot, "containers"),
	}
	_ = os.MkdirAll(s.containersDir, 0o750)
	_ = os.MkdirAll(filepath.Join(dataRoot, "workspaces"), 0o750)
	_ = os.MkdirAll(filepath.Join(dataRoot, "run"), 0o750)
	return s, nil
}

func (s *LocalService) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for id, p := range s.procs {
		if p == nil {
			continue
		}
		_ = p.Signal(syscall.SIGTERM)
		// best-effort
		_ = p.Kill()
		s.logger.Info("stopped local process", slog.String("container", id))
	}
	return nil
}

// helper: path for container metadata file
func (s *LocalService) metaPath(containerID string) string {
	return filepath.Join(s.containersDir, containerID+".json")
}

func (s *LocalService) persistInfo(id string, info ContainerInfo) error {
	b, err := json.MarshalIndent(info, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.metaPath(id), b, 0o600)
}

func (s *LocalService) loadInfo(id string) (ContainerInfo, error) {
	var info ContainerInfo
	b, err := os.ReadFile(s.metaPath(id))
	if err != nil {
		return info, err
	}
	if err := json.Unmarshal(b, &info); err != nil {
		return info, err
	}
	return info, nil
}

// Images
func (s *LocalService) PullImage(ctx context.Context, ref string, opts *PullImageOptions) (ImageInfo, error) {
	// no-op for local runner
	if ref == "" {
		return ImageInfo{}, ErrInvalidArgument
	}
	return ImageInfo{Name: ref}, nil
}

func (s *LocalService) GetImage(ctx context.Context, ref string) (ImageInfo, error) {
	// assume not present so caller may pull; return ErrInvalidArgument for empty
	if ref == "" {
		return ImageInfo{}, ErrInvalidArgument
	}
	return ImageInfo{}, fmt.Errorf("image not found: %s", ref)
}

func (s *LocalService) ListImages(ctx context.Context) ([]ImageInfo, error) { return nil, nil }
func (s *LocalService) DeleteImage(ctx context.Context, ref string, opts *DeleteImageOptions) error { return nil }
func (s *LocalService) ResolveRemoteDigest(ctx context.Context, ref string) (string, error) { return "", ErrNotSupported }

// Containers
func (s *LocalService) CreateContainer(ctx context.Context, req CreateContainerRequest) (ContainerInfo, error) {
	if req.ID == "" || req.ImageRef == "" {
		return ContainerInfo{}, ErrInvalidArgument
	}
	id := req.ID
	workdir := filepath.Join(s.dataRoot, "workspaces", id)
	if err := os.MkdirAll(workdir, 0o750); err != nil {
		return ContainerInfo{}, fmt.Errorf("create workspace dir: %w", err)
	}
	info := ContainerInfo{
		ID:          id,
		Image:       req.ImageRef,
		Labels:      req.Labels,
		Snapshotter: req.Snapshotter,
		SnapshotKey: req.SnapshotID,
		Runtime:     RuntimeInfo{Name: "local"},
		CreatedAt:   time.Now(),
		UpdatedAt:   time.Now(),
	}
	if err := s.persistInfo(id, info); err != nil {
		return ContainerInfo{}, err
	}
	return info, nil
}

func (s *LocalService) GetContainer(ctx context.Context, id string) (ContainerInfo, error) {
	return s.loadInfo(id)
}

func (s *LocalService) ListContainers(ctx context.Context) ([]ContainerInfo, error) {
	entries, err := os.ReadDir(s.containersDir)
	if err != nil {
		return nil, err
	}
	res := make([]ContainerInfo, 0, len(entries))
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		id := e.Name()
		if filepath.Ext(id) == ".json" {
			id = id[:len(id)-5]
		}
		info, err := s.loadInfo(id)
		if err != nil {
			continue
		}
		res = append(res, info)
	}
	return res, nil
}

func (s *LocalService) DeleteContainer(ctx context.Context, id string, opts *DeleteContainerOptions) error {
	_ = os.Remove(s.metaPath(id))
	_ = os.RemoveAll(filepath.Join(s.dataRoot, "workspaces", id))
	_ = os.RemoveAll(filepath.Join(s.dataRoot, "run", id))
	return nil
}

func (s *LocalService) ListContainersByLabel(ctx context.Context, key, value string) ([]ContainerInfo, error) {
	all, err := s.ListContainers(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]ContainerInfo, 0)
	for _, c := range all {
		if v, ok := c.Labels[key]; ok && v == value {
			out = append(out, c)
		}
	}
	return out, nil
}

func (s *LocalService) StartContainer(ctx context.Context, containerID string, _ *StartTaskOptions) error {
	// start bridge subprocess listening on run/<id>/bridge.sock
	info, err := s.loadInfo(containerID)
	if err != nil {
		return err
	}
	runDir := filepath.Join(s.dataRoot, "run", containerID)
	if err := os.MkdirAll(runDir, 0o750); err != nil {
		return err
	}
	sock := filepath.Join(runDir, "bridge.sock")
	_ = os.Remove(sock)

	workdir := filepath.Join(s.dataRoot, "workspaces", containerID)
	templateDir := filepath.Join(s.runtime, "templates")

	cmdPath := s.binary
	if cmdPath == "" {
		cmdPath = filepath.Join(s.runtime, "bridge")
	}
	if _, err := os.Stat(cmdPath); err != nil {
		return fmt.Errorf("bridge binary not found at %s", cmdPath)
	}
	cmd := exec.Command(cmdPath)
	env := os.Environ()
	env = append(env, fmt.Sprintf("BRIDGE_SOCKET_PATH=%s", sock))
	env = append(env, fmt.Sprintf("BRIDGE_WORKDIR=%s", workdir))
	env = append(env, fmt.Sprintf("BRIDGE_TEMPLATE_DIR=%s", templateDir))
	cmd.Env = env
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Dir = s.runtime

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start bridge: %w", err)
	}

	// record process
	s.mu.Lock()
	s.procs[containerID] = cmd.Process
	s.mu.Unlock()

	// update metadata
	info.UpdatedAt = time.Now()
	_ = s.persistInfo(containerID, info)
	return nil
}

func (s *LocalService) StopContainer(ctx context.Context, containerID string, _ *StopTaskOptions) error {
	s.mu.Lock()
	p := s.procs[containerID]
	s.mu.Unlock()
	if p == nil {
		return nil
	}
	_ = p.Signal(syscall.SIGTERM)
	_ = p.Kill()
	return nil
}

func (s *LocalService) DeleteTask(ctx context.Context, containerID string, _ *DeleteTaskOptions) error {
	return s.StopContainer(ctx, containerID, nil)
}

func (s *LocalService) GetTaskInfo(ctx context.Context, containerID string) (TaskInfo, error) {
	s.mu.Lock()
	p := s.procs[containerID]
	s.mu.Unlock()
	if p == nil {
		return TaskInfo{}, fmt.Errorf("task not found")
	}
	// check if process is alive
	if err := p.Signal(syscall.Signal(0)); err != nil {
		return TaskInfo{ContainerID: containerID, PID: uint32(p.Pid), Status: TaskStatusStopped}, nil
	}
	return TaskInfo{ContainerID: containerID, PID: uint32(p.Pid), Status: TaskStatusRunning}, nil
}

func (s *LocalService) ListTasks(ctx context.Context, opts *ListTasksOptions) ([]TaskInfo, error) {
	// return minimal info for all running procs
	res := make([]TaskInfo, 0)
	s.mu.Lock()
	for id, p := range s.procs {
		if p == nil {
			continue
		}
		res = append(res, TaskInfo{ContainerID: id, PID: uint32(p.Pid), Status: TaskStatusRunning})
	}
	s.mu.Unlock()
	return res, nil
}

func (s *LocalService) SetupNetwork(ctx context.Context, req NetworkSetupRequest) (NetworkResult, error) {
	// local runner uses host networking; return localhost
	return NetworkResult{IP: "127.0.0.1"}, nil
}

func (s *LocalService) RemoveNetwork(ctx context.Context, req NetworkSetupRequest) error { return nil }

// Snapshot and other advanced ops are not supported in local runner yet.
func (s *LocalService) CommitSnapshot(ctx context.Context, snapshotter, name, key string) error { return ErrNotSupported }
func (s *LocalService) ListSnapshots(ctx context.Context, snapshotter string) ([]SnapshotInfo, error) { return nil, ErrNotSupported }
func (s *LocalService) PrepareSnapshot(ctx context.Context, snapshotter, key, parent string) error { return ErrNotSupported }
func (s *LocalService) CreateContainerFromSnapshot(ctx context.Context, req CreateContainerRequest) (ContainerInfo, error) { return ContainerInfo{}, ErrNotSupported }
func (s *LocalService) SnapshotMounts(ctx context.Context, snapshotter, key string) ([]MountInfo, error) { return nil, ErrNotSupported }
