using System;
using UnityEngine;

namespace InfiniteStories
{
    [CreateAssetMenu(menuName = "Infinite Stories/Client settings")]
    public sealed class ClientSettings : ScriptableObject
    {
        [Tooltip("Public backend origin only. Never put provider credentials here.")]
        public string apiOrigin = "http://127.0.0.1:8042";
        public PlayerMotor playerPrefab;
        public void Validate(bool release)
        {
            if (!Uri.TryCreate(apiOrigin, UriKind.Absolute, out Uri uri) || !string.IsNullOrEmpty(uri.UserInfo) ||
                !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment) || uri.AbsolutePath != "/")
                throw new ArgumentException("Configure a public API origin without paths, credentials or query strings.");
            if (uri.Scheme != "https" && !(uri.Scheme == "http" && uri.IsLoopback && !release))
                throw new ArgumentException("The game requires HTTPS, or loopback HTTP in development.");
        }
    }
}
