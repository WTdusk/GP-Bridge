using System.Diagnostics;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

namespace GPBridgeInstaller;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        using var dialog = new InstallForm();
        Application.Run(dialog);
    }
}

internal sealed class InstallForm : Form
{
    private readonly TextBox pathBox = new();
    private readonly Button installButton = new();
    private readonly Label status = new();

    public InstallForm()
    {
        Text = "GP Bridge Setup / 安装 GP Bridge";
        Width = 620;
        Height = 280;
        MinimumSize = new System.Drawing.Size(620, 280);
        StartPosition = FormStartPosition.CenterScreen;
        Icon = LoadIcon();

        var title = new Label { Text = "GP Bridge", Font = new System.Drawing.Font("Segoe UI", 18, System.Drawing.FontStyle.Bold), AutoSize = true, Left = 28, Top = 22 };
        var subtitle = new Label { Text = "Choose an installation folder / 选择安装目录", AutoSize = true, Left = 30, Top = 66 };
        pathBox.Left = 30; pathBox.Top = 105; pathBox.Width = 440; pathBox.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "GP Bridge");
        var browse = new Button { Text = "Browse... / 浏览", Left = 480, Top = 103, Width = 100 };
        browse.Click += (_, _) => Browse();
        installButton.Text = "Install / 安装"; installButton.Left = 430; installButton.Top = 170; installButton.Width = 150; installButton.Height = 34;
        installButton.Click += (_, _) => Install();
        status.Left = 30; status.Top = 178; status.Width = 380; status.AutoSize = true;
        Controls.AddRange([title, subtitle, pathBox, browse, installButton, status]);
    }

    private void Browse()
    {
        using var dialog = new FolderBrowserDialog { SelectedPath = pathBox.Text, Description = "Select GP Bridge installation folder" };
        if (dialog.ShowDialog(this) == DialogResult.OK) pathBox.Text = dialog.SelectedPath;
    }

    private void Install()
    {
        var destination = pathBox.Text.Trim();
        if (destination.Length == 0) return;
        try
        {
            installButton.Enabled = false;
            Directory.CreateDirectory(destination);
            using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("GPBridgeInstaller.payload.zip") ?? throw new InvalidOperationException("Embedded payload missing.");
            using var archive = new ZipArchive(stream, ZipArchiveMode.Read);
            foreach (var entry in archive.Entries)
            {
                var target = Path.GetFullPath(Path.Combine(destination, entry.FullName));
                if (!target.StartsWith(Path.GetFullPath(destination) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Invalid package path.");
                if (string.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(target); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                entry.ExtractToFile(target, true);
            }
            Directory.CreateDirectory(Path.Combine(destination, "GPBridgeData", "Profiles"));
            Directory.CreateDirectory(Path.Combine(destination, "GPBridgeData", "MIDI"));
            CreateShortcut("GP Bridge.lnk", Path.Combine(destination, "GPBridge.exe"));
            status.Text = "Installed. / 安装完成。";
            Process.Start(new ProcessStartInfo(Path.Combine(destination, "GPBridge.exe")) { UseShellExecute = true });
            Close();
        }
        catch (Exception ex)
        {
            installButton.Enabled = true;
            MessageBox.Show(this, ex.Message, "GP Bridge Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void CreateShortcut(string name, string target)
    {
        var shortcutDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", "GP Bridge");
        Directory.CreateDirectory(shortcutDir);
        var script = $"$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('{Path.Combine(shortcutDir, name)}'); $sc.TargetPath = '{target}'; $sc.WorkingDirectory = '{Path.GetDirectoryName(target)}'; $sc.IconLocation = '{target},0'; $sc.Save()";
        Process.Start(new ProcessStartInfo("powershell.exe", "-NoProfile -ExecutionPolicy Bypass -Command " + script) { CreateNoWindow = true, UseShellExecute = false })?.WaitForExit();
    }

    private static System.Drawing.Icon LoadIcon()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "gpbridge.ico");
        return File.Exists(path) ? new System.Drawing.Icon(path) : System.Drawing.SystemIcons.Application;
    }
}
