using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyCompany("WTdusk")]
[assembly: AssemblyProduct("GP Bridge")]
[assembly: AssemblyCopyright("Copyright (c) 2026 WTdusk")]

internal static class LegacyInstallerProgram
{
    [STAThread]
    public static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new InstallerForm());
    }
}

internal sealed class InstallerForm : Form
{
    private readonly TextBox path = new TextBox();
    private readonly Button install = new Button();
    private readonly Label status = new Label();

    public InstallerForm()
    {
        Text = "GP Bridge Setup / 安装 GP Bridge";
        ClientSize = new Size(590, 220);
        StartPosition = FormStartPosition.CenterScreen;
        Icon = SystemIcons.Application;
        var title = new Label { Text = "GP Bridge", Font = new Font("Segoe UI", 18, FontStyle.Bold), AutoSize = true, Left = 28, Top = 22 };
        var subtitle = new Label { Text = "Choose an installation folder / 选择安装目录", AutoSize = true, Left = 30, Top = 66 };
        path.Left = 30; path.Top = 105; path.Width = 440;
        path.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "GP Bridge");
        var browse = new Button { Text = "Browse... / 浏览", Left = 480, Top = 103, Width = 100 };
        browse.Click += delegate { using (var d = new FolderBrowserDialog { SelectedPath = path.Text }) if (d.ShowDialog(this) == DialogResult.OK) path.Text = d.SelectedPath; };
        install.Text = "Install / 安装"; install.Left = 430; install.Top = 164; install.Width = 150; install.Height = 34;
        install.Click += delegate { Install(); };
        status.Left = 30; status.Top = 174; status.Width = 380; status.AutoSize = true;
        Controls.AddRange(new Control[] { title, subtitle, path, browse, install, status });
    }

    private void Install()
    {
        try
        {
            install.Enabled = false;
            var destination = path.Text.Trim();
            if (destination.Length == 0) throw new InvalidOperationException("Please choose an installation folder.");
            Directory.CreateDirectory(destination);
            using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
            {
                if (stream == null) throw new InvalidOperationException("Embedded package is missing.");
                using (var archive = new ZipArchive(stream, ZipArchiveMode.Read))
                foreach (var entry in archive.Entries)
                {
                    var target = Path.GetFullPath(Path.Combine(destination, entry.FullName));
                    if (!target.StartsWith(Path.GetFullPath(destination) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Invalid package path.");
                    if (String.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(target); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    entry.ExtractToFile(target, true);
                }
            }
            Directory.CreateDirectory(Path.Combine(destination, "GPBridgeData", "Profiles"));
            Directory.CreateDirectory(Path.Combine(destination, "GPBridgeData", "MIDI"));
            status.Text = "Installed. / 安装完成。";
            Process.Start(Path.Combine(destination, "GPBridge.exe"));
            Close();
        }
        catch (Exception ex) { install.Enabled = true; MessageBox.Show(this, ex.Message, "GP Bridge Setup", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }
}
