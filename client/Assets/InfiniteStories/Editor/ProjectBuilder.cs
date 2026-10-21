using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace InfiniteStories.Editor
{
    public static class ProjectBuilder
    {
        [MenuItem("Infinite Stories/Prepare chapter scene")]
        public static void Prepare()
        {
            Directory.CreateDirectory("Assets/InfiniteStories/Resources");
            Directory.CreateDirectory("Assets/InfiniteStories/Scenes");
            Directory.CreateDirectory("Assets/InfiniteStories/Prefabs");
            const string settingsPath="Assets/InfiniteStories/Resources/ClientSettings.asset";
            var settings=AssetDatabase.LoadAssetAtPath<ClientSettings>(settingsPath);
            if (settings==null) { settings=ScriptableObject.CreateInstance<ClientSettings>(); AssetDatabase.CreateAsset(settings,settingsPath); }
            string origin=Environment.GetEnvironmentVariable("IS_PUBLIC_API_URL");
            if (!string.IsNullOrWhiteSpace(origin)) settings.apiOrigin=origin;
            settings.Validate(false); EditorUtility.SetDirty(settings);
            // Create an authored player prefab without replacing an existing one.
            const string prefabPath="Assets/InfiniteStories/Prefabs/Traveler.prefab";
            if (AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath)==null)
            { var player=new GameObject("Traveler"); player.AddComponent<PlayerMotor>(); PrefabUtility.SaveAsPrefabAsset(player,prefabPath); UnityEngine.Object.DestroyImmediate(player); }
            settings.playerPrefab=AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath).GetComponent<PlayerMotor>();
            const string scenePath="Assets/InfiniteStories/Scenes/Chapter.unity";
            if (!File.Exists(scenePath))
            {
                var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
                var root=new GameObject("Infinite Stories"); var client=root.AddComponent<GameClient>(); client.settings=settings;
                EditorSceneManager.SaveScene(scene,scenePath);
            }
            PlayerSettings.companyName="Infinite Stories"; PlayerSettings.productName="Infinite Stories: The Last Light";
            PlayerSettings.defaultScreenWidth=1280; PlayerSettings.defaultScreenHeight=720;
            PlayerSettings.runInBackground=true; PlayerSettings.colorSpace=ColorSpace.Linear;
            PlayerSettings.WebGL.compressionFormat=WebGLCompressionFormat.Disabled;
            PlayerSettings.WebGL.dataCaching=true;
            PlayerSettings.WebGL.template="PROJECT:Accessible";
            EditorBuildSettings.scenes=new[] { new EditorBuildSettingsScene(scenePath,true) };
            AssetDatabase.SaveAssets(); AssetDatabase.Refresh();
        }

        public static void BuildWeb()
        {
            BuildWebPlayer(false);
        }

        // A real local capability check; this artifact is not a release build.
        public static void BuildDevelopmentWeb()
        {
            BuildWebPlayer(true);
        }

        public static void BuildCulturalVerificationWeb()
        {
            var settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset");
            string original=settings!=null ? settings.apiOrigin : "http://127.0.0.1:8042";
            try { BuildWebPlayer(true,"Builds/CulturalVerification"); }
            finally { settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset"); if(settings!=null){ settings.apiOrigin=original; EditorUtility.SetDirty(settings); AssetDatabase.SaveAssets(); } }
        }
        public static void BuildVisualVerificationWeb()
        {
            var settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset");
            string original=settings.apiOrigin;
            try { BuildWebPlayer(true,"Builds/VisualVerification"); }
            finally { settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset"); if(settings!=null){settings.apiOrigin=original;EditorUtility.SetDirty(settings);AssetDatabase.SaveAssets();} }
        }
        public static void BuildPhase2BWeb()
        {
            var settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset");string original=settings.apiOrigin;
            try{BuildWebPlayer(true,"Builds/Phase2B");}
            finally{settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset");if(settings!=null){settings.apiOrigin=original;EditorUtility.SetDirty(settings);AssetDatabase.SaveAssets();}}
        }
        public static void BuildPlayerPresentationWeb()
        {
            var settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset");string original=settings.apiOrigin;
            try{BuildWebPlayer(true,"Builds/PlayerPresentation",true);}
            finally{settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset");if(settings!=null){settings.apiOrigin=original;EditorUtility.SetDirty(settings);AssetDatabase.SaveAssets();}}
        }
        public static void BuildInvestigationWeb()
        {
            var settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset");string original=settings.apiOrigin;
            try{BuildWebPlayer(true,"Builds/Investigation",true);}
            finally{settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset");if(settings!=null){settings.apiOrigin=original;EditorUtility.SetDirty(settings);AssetDatabase.SaveAssets();}}
        }
        static void BuildWebPlayer(bool development, string output=null,bool cleanPreview=false)
        {
            Prepare();
            var settings=AssetDatabase.LoadAssetAtPath<ClientSettings>("Assets/InfiniteStories/Resources/ClientSettings.asset");
            settings.Validate(!development);
            if (!BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.WebGL,BuildTarget.WebGL))
                throw new BuildFailedException("Web Build Support is not installed.");
            var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions {
                scenes=new[] { "Assets/InfiniteStories/Scenes/Chapter.unity" },
                locationPathName=output ?? (development ? "Builds/WebDevelopment" : "Builds/Web"), target=BuildTarget.WebGL,
                extraScriptingDefines=cleanPreview ? new[]{"INFINITE_STORIES_LOCAL_PREVIEW"}:Array.Empty<string>(),
                options=development&&!cleanPreview ? BuildOptions.Development : BuildOptions.None });
            if (report.summary.result!=BuildResult.Succeeded) throw new BuildFailedException("The Unity Web build failed; inspect the Editor log.");
            Debug.Log($"Infinite Stories Web build succeeded: development={development&&!cleanPreview}; localPreview={cleanPreview}; bytes={report.summary.totalSize}");
        }
    }
}
