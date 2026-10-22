using System;
using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace InfiniteStories.Tests
{
    // Real local HTTP, captured Qloo only. Saves/preferences are isolated/restored.
    public sealed class GenerationRecoveryTests
    {
        [UnityTest] public IEnumerator ReloadRestoresPriorSaveAndFencesLateCreation(){yield return Scenario("reload");}
        [UnityTest] public IEnumerator ResumeRestoresPriorSaveAndFencesLateCreation(){yield return Scenario("resume");}
        [UnityTest] public IEnumerator RetryReconcilesCreationWithoutGeneratingAgain(){yield return Scenario("retry");}
        [UnityTest] public IEnumerator NoSaveRecoveryClearsOnlyConfirmedCancelledCreation(){yield return Scenario("none");}
        [UnityTest] public IEnumerator LostCreationResponseRecoversItsRunInsteadOfPriorSave(){yield return Scenario("completed");}
        [UnityTest] public IEnumerator ReloadKeepsUncertainActionReceiptUntilExplicitRetry(){yield return Scenario("action");}

        static IEnumerator Scenario(string scenario)
        {
            if(Environment.GetEnvironmentVariable("IS_UNITY_HTTP_TESTS")!="1"||Environment.GetEnvironmentVariable("IS_UNITY_CULTURAL_TESTS")!="1")
                Assert.Ignore("Requires explicitly captured-only local HTTP verification server.");
            string[] keys={"is.resumeToken","is.sessionId","is.pendingRequest"};
            string[] prior=Array.ConvertAll(keys,k=>PlayerPrefs.GetString(k,""));
            foreach(string key in keys)PlayerPrefs.DeleteKey(key);
            var settings=ScriptableObject.CreateInstance<ClientSettings>();settings.apiOrigin=Environment.GetEnvironmentVariable("IS_UNITY_TEST_API_URL");
            GameObject root=null;
            try{
                root=new GameObject("Isolated generation recovery client");var client=root.AddComponent<GameClient>();client.settings=settings;yield return null;
                var api=root.GetComponent<ApiTransport>();var ui=root.GetComponent<GameUI>();var world=root.GetComponent<TileWorld>();
                float deadline=Time.realtimeSinceStartup+10;while(!ui.CulturalAvailable&&Time.realtimeSinceStartup<deadline)yield return null;
                Assert.IsTrue(ui.ReplayVerification,"Never exercise live Qloo through these client tests.");
                GameView saved=null;
                if(scenario!="none"){
                    yield return api.Send("/v1/sessions","POST",JsonUtility.ToJson(new NewGameRequest{request_id=Guid.NewGuid().ToString(),mode="authored",interests=new Interest[0]}),v=>saved=v,(e,_)=>Assert.Fail(e.code));
                    foreach(var point in new[]{new Vector2(4,8),new Vector2(7,8),new Vector2(10,8),new Vector2(13,8),new Vector2(14,9)}){
                        yield return api.Send("/v1/sessions/"+saved.session_id+"/actions","POST",JsonUtility.ToJson(new ActionRequest{request_id=Guid.NewGuid().ToString(),expected_revision=saved.revision,command=new Command{kind="position",x=point.x,y=point.y}}),v=>saved=v,(e,_)=>Assert.Fail(e.code));
                    }
                    yield return api.Send("/v1/sessions/"+saved.session_id+"/actions","POST",JsonUtility.ToJson(new ActionRequest{request_id=Guid.NewGuid().ToString(),expected_revision=saved.revision,command=new Command{kind="choose",target="mara",choice="take_map"}}),v=>saved=v,(e,_)=>Assert.Fail(e.code));
                    PlayerPrefs.SetString("is.sessionId",saved.session_id);ui.Resume.Invoke();
                    deadline=Time.realtimeSinceStartup+10;while(world.Player==null&&Time.realtimeSinceStartup<deadline)yield return null;Assert.IsNotNull(world.Player);
                }
                var creation=new NewGameRequest{request_id=Guid.NewGuid().ToString(),mode="cultural",interests=new[]{new Interest{name="David Bowie",category="artist"}}};
                string path="/v1/sessions",json=JsonUtility.ToJson(creation);
                if(scenario=="completed"){
                    yield return api.Send(path,"POST",json,v=>saved=v,(e,_)=>Assert.Fail(e.code));
                    Assert.AreEqual("cultural",saved.state.mode);Assert.IsNotNull(saved.state.cultural_context);
                    // Response never reaches GameClient.Accept: its old save link survives.
                }
                if(scenario=="action"){
                    path="/v1/sessions/"+saved.session_id+"/actions";
                    json=JsonUtility.ToJson(new ActionRequest{request_id=Guid.NewGuid().ToString(),expected_revision=saved.revision,command=new Command{kind="position",x=15,y=9}});
                    yield return api.Send(path,"POST",json,v=>saved=v,(e,_)=>Assert.Fail(e.code));
                }
                PlayerPrefs.SetString("is.pendingRequest",JsonUtility.ToJson(new PendingRequest{path=path,method="POST",json=json}));PlayerPrefs.Save();
                if(scenario=="resume"||scenario=="none"||scenario=="completed"){
                    UnityEngine.Object.Destroy(root);yield return null;
                    root=new GameObject("Reloaded client with persisted pending creation");client=root.AddComponent<GameClient>();client.settings=settings;yield return null;
                    api=root.GetComponent<ApiTransport>();ui=root.GetComponent<GameUI>();world=root.GetComponent<TileWorld>();
                }
                if(scenario=="resume"||scenario=="none")ui.Resume.Invoke();else if(scenario=="retry")ui.Retry.Invoke();else ui.Reload.Invoke();
                deadline=Time.realtimeSinceStartup+12;
                if(scenario=="action"){
                    while((world.Player==null||Vector2.Distance(world.Player.Position,new Vector2(15,9))>.05f)&&Time.realtimeSinceStartup<deadline)yield return null;
                    Assert.IsTrue(client.HasPending,"A GET must not discard an uncertain action receipt.");
                    Assert.That(Vector2.Distance(world.Player.Position,new Vector2(15,9)),Is.LessThan(.05f));
                    yield return null;ui.Retry.Invoke();
                }
                while(client.HasPending&&Time.realtimeSinceStartup<deadline)yield return null;
                Assert.IsFalse(client.HasPending,"Recovery must not leave a creation/retry trap.");yield return null;
                if(scenario=="none"){
                    Assert.IsTrue(ui.TitleVisible);Assert.IsNull(world.Player,"Interrupted evidence is not an initialized run.");
                    ui.StartAuthored.Invoke();deadline=Time.realtimeSinceStartup+10;while(world.Player==null&&Time.realtimeSinceStartup<deadline)yield return null;Assert.IsNotNull(world.Player,"Player can deliberately start again after terminal recovery.");
                }else{
                    Assert.AreEqual(saved.session_id,PlayerPrefs.GetString("is.sessionId"));GameView restored=null;
                    yield return api.Send("/v1/sessions/"+saved.session_id,"GET",null,v=>restored=v,(e,_)=>Assert.Fail(e.code));
                    Assert.AreEqual(JsonUtility.ToJson(saved.state),JsonUtility.ToJson(restored.state));Assert.AreEqual(saved.revision,restored.revision);
                    Assert.IsFalse(ui.TitleVisible);
                }
                if(scenario!="completed"&&scenario!="action"){
                    ApiError terminal=null;yield return api.Send("/v1/sessions","POST",JsonUtility.ToJson(creation),_=>Assert.Fail("Cancelled creation must never restart"),(e,_)=>terminal=e);
                    Assert.AreEqual("QLOO_GENERATION_INTERRUPTED",terminal?.code);
                }
            }finally{
                if(root!=null)UnityEngine.Object.Destroy(root);UnityEngine.Object.Destroy(settings);
                for(int i=0;i<keys.Length;i++)if(prior[i].Length==0)PlayerPrefs.DeleteKey(keys[i]);else PlayerPrefs.SetString(keys[i],prior[i]);PlayerPrefs.Save();
            }
        }
    }
}
