// SYNTHETIC board_verification.json fixture (fake_board: true): hw2 changed-machine-twin traces, every 30th step,
// with disturbance_at set to pre_s. Not a board run. Typed so `tsc` checks it against the contract in api.ts.
import type { BoardVerification } from "../api";

export const BOARD_VERIFICATION_FIXTURE: BoardVerification = {
 "trials": [
  {
   "label": "v1",
   "controller_sha256": "84f4bfbfd9b3a0ba3c37fd48962497862a5a6e702ca777f8976ecb660745eae2",
   "trace": {
    "steps": [
     {
      "t": 0.0,
      "y": 0.08305096054911468,
      "h_true": 0.08234227639596346,
      "u_requested": 0.5742434977446051,
      "u_applied": 0.5742434977446051,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 30.0,
      "y": 0.09182351223525582,
      "h_true": 0.09567893437272879,
      "u_requested": 0.5740898251909163,
      "u_applied": 0.5740898251909163,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 60.0,
      "y": 0.18857461494462768,
      "h_true": 0.17925398971257328,
      "u_requested": 0.5340164805499104,
      "u_applied": 0.5340164805499104,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 90.0,
      "y": 0.23619888960866825,
      "h_true": 0.24212716584874733,
      "u_requested": 0.4916590362245165,
      "u_applied": 0.4916590362245165,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 120.0,
      "y": 0.27806620841649526,
      "h_true": 0.285621314585703,
      "u_requested": 0.46176772470239424,
      "u_applied": 0.46176772470239424,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 150.0,
      "y": 0.3195630672126666,
      "h_true": 0.31493362486985366,
      "u_requested": 0.4412308659686083,
      "u_applied": 0.4412308659686083,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 180.0,
      "y": 0.32706709750117446,
      "h_true": 0.33479354566753583,
      "u_requested": 0.42498944911077685,
      "u_applied": 0.42498944911077685,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 210.0,
      "y": 0.36399561614106435,
      "h_true": 0.3479747266369007,
      "u_requested": 0.41600856203822295,
      "u_applied": 0.41600856203822295,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 240.0,
      "y": 0.36152777414956955,
      "h_true": 0.3569588188739973,
      "u_requested": 0.41229954309552497,
      "u_applied": 0.41229954309552497,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 270.0,
      "y": 0.34975262648645233,
      "h_true": 0.3631924166050593,
      "u_requested": 0.4099716246062222,
      "u_applied": 0.4099716246062222,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 300.0,
      "y": 0.3671093943310743,
      "h_true": 0.36768739988093824,
      "u_requested": 0.40548679753085864,
      "u_applied": 0.40548679753085864,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 330.0,
      "y": 0.35282514543104476,
      "h_true": 0.3705413274698358,
      "u_requested": 0.40497419041900934,
      "u_applied": 0.40497419041900934,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 360.0,
      "y": 0.3712727824532193,
      "h_true": 0.3726324248319162,
      "u_requested": 0.4022732317626366,
      "u_applied": 0.4022732317626366,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 390.0,
      "y": 0.36495020505936393,
      "h_true": 0.3738510887106069,
      "u_requested": 0.39977143808624505,
      "u_applied": 0.39977143808624505,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 420.0,
      "y": 0.3787176389271362,
      "h_true": 0.3745855355461727,
      "u_requested": 0.40187195770960404,
      "u_applied": 0.40187195770960404,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 450.0,
      "y": 0.3806700496311195,
      "h_true": 0.375254436059151,
      "u_requested": 0.3980781034626617,
      "u_applied": 0.3980781034626617,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 480.0,
      "y": 0.3760113970666388,
      "h_true": 0.3754293062437567,
      "u_requested": 0.3975761336664018,
      "u_applied": 0.3975761336664018,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 510.0,
      "y": 0.3842490049164804,
      "h_true": 0.37539233034216535,
      "u_requested": 0.39890077966954257,
      "u_applied": 0.39890077966954257,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 540.0,
      "y": 0.38954569974923925,
      "h_true": 0.3757495689192031,
      "u_requested": 0.3963120499108257,
      "u_applied": 0.3963120499108257,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 570.0,
      "y": 0.3691801634138249,
      "h_true": 0.3757138211879653,
      "u_requested": 0.3973199839300994,
      "u_applied": 0.3973199839300994,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 600.0,
      "y": 0.3763207810774711,
      "h_true": 0.3756241252562114,
      "u_requested": 0.39933592103186105,
      "u_applied": 0.39933592103186105,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 630.0,
      "y": 0.36489525561230896,
      "h_true": 0.37578265265464317,
      "u_requested": 0.39924662069393047,
      "u_applied": 0.39924662069393047,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 660.0,
      "y": 0.38609999801907585,
      "h_true": 0.3759437139312138,
      "u_requested": 0.39920267696415535,
      "u_applied": 0.39920267696415535,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 690.0,
      "y": 0.38620408379652416,
      "h_true": 0.37599022625806205,
      "u_requested": 0.39736477105951734,
      "u_applied": 0.39736477105951734,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 720.0,
      "y": 0.36701292976425487,
      "h_true": 0.3759758329067944,
      "u_requested": 0.39865611943705004,
      "u_applied": 0.39865611943705004,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 750.0,
      "y": 0.37331090978301584,
      "h_true": 0.37584387947922265,
      "u_requested": 0.3983139331842455,
      "u_applied": 0.3983139331842455,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 780.0,
      "y": 0.38283432416614666,
      "h_true": 0.3758646521093348,
      "u_requested": 0.3982331529323439,
      "u_applied": 0.3982331529323439,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 810.0,
      "y": 0.37438105160332535,
      "h_true": 0.3758123360923883,
      "u_requested": 0.39687431501436915,
      "u_applied": 0.39687431501436915,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 840.0,
      "y": 0.39284698244030253,
      "h_true": 0.37569055207881086,
      "u_requested": 0.39546683667964655,
      "u_applied": 0.39546683667964655,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 870.0,
      "y": 0.37448383009852526,
      "h_true": 0.37556567968655097,
      "u_requested": 0.39827980307522287,
      "u_applied": 0.39827980307522287,
      "override": false,
      "reason": "ok"
     }
    ],
    "dt": 1.0,
    "target": 0.5,
    "disturbance_at": 300.0,
    "meta": {
     "seed": 7,
     "scenario": 1000,
     "controller": "hw2-20261103-074537-698ba8-v1",
     "isolation": "docker",
     "disturbance": null,
     "duration_s": 900.0,
     "board_verification": {
      "label": "v1",
      "plant": "board"
     },
     "synthetic": true
    }
   },
   "post_mae": 0.12525345551775283,
   "post_in_band": 0.0,
   "overrides": 0,
   "hard_violations": 0,
   "invalid_outputs": 0,
   "interlock_hit": false,
   "start_T_display": 19.98305763294688
  },
  {
   "label": "v2",
   "controller_sha256": "e77ce10ab4e0238ab188078c5e429fb4ca72cf412e2b67ecab50c2bce652bb8e",
   "trace": {
    "steps": [
     {
      "t": 0.0,
      "y": 0.08305096054911468,
      "h_true": 0.08234227639596346,
      "u_requested": 0.6159384016896937,
      "u_applied": 0.6159384016896937,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 30.0,
      "y": 0.09279229255699335,
      "h_true": 0.09664771469446631,
      "u_requested": 0.6156120502505684,
      "u_applied": 0.6156120502505684,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 60.0,
      "y": 0.19560453213922768,
      "h_true": 0.18628390690717328,
      "u_requested": 0.565529766960331,
      "u_applied": 0.565529766960331,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 90.0,
      "y": 0.247123123876003,
      "h_true": 0.25305140011608207,
      "u_requested": 0.5128062073958387,
      "u_applied": 0.5128062073958387,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 120.0,
      "y": 0.29046956579167527,
      "h_true": 0.298024671960883,
      "u_requested": 0.5489347322834762,
      "u_applied": 0.5489347322834762,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 150.0,
      "y": 0.33755827776779923,
      "h_true": 0.3329288354249863,
      "u_requested": 0.6114431216168501,
      "u_applied": 0.6114431216168501,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 180.0,
      "y": 0.36272801239973285,
      "h_true": 0.3704544605660942,
      "u_requested": 0.6537851255659729,
      "u_applied": 0.6537851255659729,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 210.0,
      "y": 0.42389456231644823,
      "h_true": 0.4078736728122846,
      "u_requested": 0.6822508111025036,
      "u_applied": 0.6822508111025036,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 240.0,
      "y": 0.44745233648302635,
      "h_true": 0.4428833812074541,
      "u_requested": 0.6985878822500373,
      "u_applied": 0.6985878822500373,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 270.0,
      "y": 0.460292987341679,
      "h_true": 0.47373277746028597,
      "u_requested": 0.7029211482617688,
      "u_applied": 0.7029211482617688,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 300.0,
      "y": 0.4989233527110327,
      "h_true": 0.49950135826089664,
      "u_requested": 0.6922261519157928,
      "u_applied": 0.6922261519157928,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 330.0,
      "y": 0.5012846492241606,
      "h_true": 0.5190008312629516,
      "u_requested": 0.6788659569280555,
      "u_applied": 0.6788659569280555,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 360.0,
      "y": 0.5313908579215265,
      "h_true": 0.5327505003002234,
      "u_requested": 0.6573014054405393,
      "u_applied": 0.6573014054405393,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 390.0,
      "y": 0.5317904693062037,
      "h_true": 0.5406913529574466,
      "u_requested": 0.6331764203224008,
      "u_applied": 0.6331764203224008,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 420.0,
      "y": 0.5478014687250301,
      "h_true": 0.5436693653440666,
      "u_requested": 0.6153618973514265,
      "u_applied": 0.6153618973514265,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 450.0,
      "y": 0.5484110166581618,
      "h_true": 0.5429954030861933,
      "u_requested": 0.5911629858412205,
      "u_applied": 0.5911629858412205,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 480.0,
      "y": 0.5396520165473871,
      "h_true": 0.5390699257245051,
      "u_requested": 0.5725968025502368,
      "u_applied": 0.5725968025502368,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 510.0,
      "y": 0.5417708017948749,
      "h_true": 0.5329141272205599,
      "u_requested": 0.5615810423084915,
      "u_applied": 0.5615810423084915,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 540.0,
      "y": 0.5400437350056919,
      "h_true": 0.5262476041756557,
      "u_requested": 0.5485479229496081,
      "u_applied": 0.5485479229496081,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 570.0,
      "y": 0.5124291407863454,
      "h_true": 0.5189627985604858,
      "u_requested": 0.542342120227036,
      "u_applied": 0.542342120227036,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 600.0,
      "y": 0.5125166185132122,
      "h_true": 0.5118199626919525,
      "u_requested": 0.541751972536028,
      "u_applied": 0.541751972536028,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 630.0,
      "y": 0.4948382067998256,
      "h_true": 0.5057256038421598,
      "u_requested": 0.5417964932724288,
      "u_applied": 0.5417964932724288,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 660.0,
      "y": 0.5109514995995637,
      "h_true": 0.5007952155117016,
      "u_requested": 0.54328590149438,
      "u_applied": 0.54328590149438,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 690.0,
      "y": 0.5071265744820732,
      "h_true": 0.4969127169436111,
      "u_requested": 0.544009554053323,
      "u_applied": 0.544009554053323,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 720.0,
      "y": 0.4851923265765467,
      "h_true": 0.49415522971908626,
      "u_requested": 0.5483111688459167,
      "u_applied": 0.5483111688459167,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 750.0,
      "y": 0.48968790914393007,
      "h_true": 0.4922208788401369,
      "u_requested": 0.5519885655952768,
      "u_applied": 0.5519885655952768,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 780.0,
      "y": 0.4983619843819255,
      "h_true": 0.49139231232511366,
      "u_requested": 0.5556285957210423,
      "u_applied": 0.5556285957210423,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 810.0,
      "y": 0.4897986388149571,
      "h_true": 0.49122992330402004,
      "u_requested": 0.5572806480917609,
      "u_applied": 0.5572806480917609,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 840.0,
      "y": 0.5087045097335572,
      "h_true": 0.4915480793720655,
      "u_requested": 0.5582254316088702,
      "u_applied": 0.5582254316088702,
      "override": false,
      "reason": "ok"
     },
     {
      "t": 870.0,
      "y": 0.49109204439144066,
      "h_true": 0.49217389397946637,
      "u_requested": 0.5637883654105076,
      "u_applied": 0.5637883654105076,
      "override": false,
      "reason": "ok"
     }
    ],
    "dt": 1.0,
    "target": 0.5,
    "disturbance_at": 300.0,
    "meta": {
     "seed": 7,
     "scenario": 1000,
     "controller": "hw2-20261103-074537-698ba8-v2",
     "isolation": "docker",
     "disturbance": null,
     "duration_s": 900.0,
     "board_verification": {
      "label": "v2",
      "plant": "board"
     },
     "synthetic": true
    }
   },
   "post_mae": 0.018275414896675272,
   "post_in_band": 1.0,
   "overrides": 0,
   "hard_violations": 0,
   "invalid_outputs": 0,
   "interlock_hit": false,
   "start_T_display": 19.98305763294688
  }
 ],
 "order": [
  "v1",
  "v2"
 ],
 "pre_s": 300.0,
 "post_s": 600.0,
 "disturbance": {
  "family": "heater_derate",
  "magnitude": 0.6,
  "applied_by": "trusted_actuator",
  "at_t": 300.0
 },
 "comparison": {
  "post_mae_v1": 0.12525345551775283,
  "post_mae_v2": 0.018275414896675272,
  "reduction": 0.8540925292549314,
  "in_band_v1": 0.0,
  "in_band_v2": 1.0
 },
 "twin_prediction": {
  "prediction_basis": "SYNTHETIC: changed-machine twin, episode 1 traces",
  "trials": [
   {
    "label": "v1",
    "controller_sha256": "84f4bfbfd9b3a0ba3c37fd48962497862a5a6e702ca777f8976ecb660745eae2",
    "trace": {
     "steps": [
      {
       "t": 0.0,
       "y": 0.09010554177213255,
       "h_true": 0.08234227639596346,
       "u_requested": 0.5700107490107945,
       "u_applied": 0.5700107490107945,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 30.0,
       "y": 0.0861688732655362,
       "h_true": 0.0955761381305687,
       "u_requested": 0.5721355831521093,
       "u_applied": 0.5721355831521093,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 60.0,
       "y": 0.17239924646552868,
       "h_true": 0.17893061095815893,
       "u_requested": 0.5332533454111612,
       "u_applied": 0.5332533454111612,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 90.0,
       "y": 0.25136837345660845,
       "h_true": 0.2415927095946357,
       "u_requested": 0.4898230521015585,
       "u_applied": 0.4898230521015585,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 120.0,
       "y": 0.2808390183852015,
       "h_true": 0.2852630830044956,
       "u_requested": 0.4607981936232452,
       "u_applied": 0.4607981936232452,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 150.0,
       "y": 0.30516237016637443,
       "h_true": 0.3144639813614412,
       "u_requested": 0.44280792449740547,
       "u_applied": 0.44280792449740547,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 180.0,
       "y": 0.33278414053227456,
       "h_true": 0.33444035300242364,
       "u_requested": 0.4262034234322744,
       "u_applied": 0.4262034234322744,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 210.0,
       "y": 0.3443218351829132,
       "h_true": 0.3478154932025273,
       "u_requested": 0.4176857354793596,
       "u_applied": 0.4176857354793596,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 240.0,
       "y": 0.3654854424542706,
       "h_true": 0.3567808608116051,
       "u_requested": 0.412111685160439,
       "u_applied": 0.412111685160439,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 270.0,
       "y": 0.37062198051242307,
       "h_true": 0.3630014665682385,
       "u_requested": 0.4073086882733497,
       "u_applied": 0.4073086882733497,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 300.0,
       "y": 0.3835409486395066,
       "h_true": 0.3672338569206793,
       "u_requested": 0.4049631524941171,
       "u_applied": 0.4049631524941171,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 330.0,
       "y": 0.3638861564672509,
       "h_true": 0.3701170464837235,
       "u_requested": 0.40218919996757174,
       "u_applied": 0.40218919996757174,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 360.0,
       "y": 0.3751118258745049,
       "h_true": 0.37202271132752507,
       "u_requested": 0.4004789368508413,
       "u_applied": 0.4004789368508413,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 390.0,
       "y": 0.377625536594977,
       "h_true": 0.3734138674315662,
       "u_requested": 0.3989456707909561,
       "u_applied": 0.3989456707909561,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 420.0,
       "y": 0.36558089545578926,
       "h_true": 0.3742181644715044,
       "u_requested": 0.4007952099651667,
       "u_applied": 0.4007952099651667,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 450.0,
       "y": 0.37250235062737647,
       "h_true": 0.3749463179744031,
       "u_requested": 0.3974267451868505,
       "u_applied": 0.3974267451868505,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 480.0,
       "y": 0.34964571491316315,
       "h_true": 0.37520837710881527,
       "u_requested": 0.39991176030028475,
       "u_applied": 0.39991176030028475,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 510.0,
       "y": 0.38340669823092405,
       "h_true": 0.37539393911563196,
       "u_requested": 0.39962939523869406,
       "u_applied": 0.39962939523869406,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 540.0,
       "y": 0.3814304473870096,
       "h_true": 0.37575802410601844,
       "u_requested": 0.39947586074859287,
       "u_applied": 0.39947586074859287,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 570.0,
       "y": 0.37332901447197503,
       "h_true": 0.3760151548532388,
       "u_requested": 0.39705865822812064,
       "u_applied": 0.39705865822812064,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 600.0,
       "y": 0.37863709584047023,
       "h_true": 0.37606510551594785,
       "u_requested": 0.39921276216022256,
       "u_applied": 0.39921276216022256,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 630.0,
       "y": 0.3664478604749649,
       "h_true": 0.3762420852799999,
       "u_requested": 0.4000893765255614,
       "u_applied": 0.4000893765255614,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 660.0,
       "y": 0.3628421094219131,
       "h_true": 0.3763275970778043,
       "u_requested": 0.39831591386921655,
       "u_applied": 0.39831591386921655,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 690.0,
       "y": 0.38114862341537165,
       "h_true": 0.37629165264778264,
       "u_requested": 0.39812071648664626,
       "u_applied": 0.39812071648664626,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 720.0,
       "y": 0.36718453165581333,
       "h_true": 0.37622123399993246,
       "u_requested": 0.3990367119429208,
       "u_applied": 0.3990367119429208,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 750.0,
       "y": 0.3722500784144537,
       "h_true": 0.37615772065481357,
       "u_requested": 0.39821379529496337,
       "u_applied": 0.39821379529496337,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 780.0,
       "y": 0.3673295614078109,
       "h_true": 0.37603828978489917,
       "u_requested": 0.3965790019952701,
       "u_applied": 0.3965790019952701,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 810.0,
       "y": 0.3594007691813187,
       "h_true": 0.37587854358525435,
       "u_requested": 0.40021539937530404,
       "u_applied": 0.40021539937530404,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 840.0,
       "y": 0.3749844837682158,
       "h_true": 0.375865788735796,
       "u_requested": 0.3981628464445087,
       "u_applied": 0.3981628464445087,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 870.0,
       "y": 0.38686690481155867,
       "h_true": 0.37592453403674053,
       "u_requested": 0.39869736729890265,
       "u_applied": 0.39869736729890265,
       "override": false,
       "reason": "ok"
      }
     ],
     "dt": 1.0,
     "target": 0.5,
     "disturbance_at": 300.0,
     "meta": {
      "seed": 7,
      "scenario": 1001,
      "controller": "hw2-20261103-074537-698ba8-v1",
      "isolation": "docker",
      "disturbance": null,
      "duration_s": 900.0,
      "board_verification": {
       "label": "v1",
       "plant": "twin"
      },
      "synthetic": true
     }
    },
    "post_mae": 0.12523299944439617,
    "post_in_band": 0.0,
    "overrides": 0,
    "hard_violations": 0,
    "invalid_outputs": 0,
    "interlock_hit": false
   },
   {
    "label": "v2",
    "controller_sha256": "e77ce10ab4e0238ab188078c5e429fb4ca72cf412e2b67ecab50c2bce652bb8e",
    "trace": {
     "steps": [
      {
       "t": 0.0,
       "y": 0.09010554177213255,
       "h_true": 0.08234227639596346,
       "u_requested": 0.6110001948335813,
       "u_applied": 0.6110001948335813,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 30.0,
       "y": 0.08712052088024698,
       "h_true": 0.09652778574527948,
       "u_requested": 0.613334647566276,
       "u_applied": 0.613334647566276,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 60.0,
       "y": 0.17937538640868594,
       "h_true": 0.1859067509013162,
       "u_requested": 0.5645213097177308,
       "u_applied": 0.5645213097177308,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 90.0,
       "y": 0.26219537707779567,
       "h_true": 0.2524197132158229,
       "u_requested": 0.5106672999282591,
       "u_applied": 0.5106672999282591,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 120.0,
       "y": 0.2931655329124311,
       "h_true": 0.2975895975317252,
       "u_requested": 0.5550040025929703,
       "u_applied": 0.5550040025929703,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 150.0,
       "y": 0.3240236206212985,
       "h_true": 0.3333252318163653,
       "u_requested": 0.6196870784681204,
       "u_applied": 0.6196870784681204,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 180.0,
       "y": 0.37013580761292314,
       "h_true": 0.3717920200830722,
       "u_requested": 0.6613795236063416,
       "u_applied": 0.6613795236063416,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 210.0,
       "y": 0.40653641545431773,
       "h_true": 0.41003007347393183,
       "u_requested": 0.6887532443010383,
       "u_applied": 0.6887532443010383,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 240.0,
       "y": 0.4540365604560528,
       "h_true": 0.44533197881338726,
       "u_requested": 0.7014173879940346,
       "u_applied": 0.7014173879940346,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 270.0,
       "y": 0.48377481651267207,
       "h_true": 0.4761543025684875,
       "u_requested": 0.7002592819841008,
       "u_applied": 0.7002592819841008,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 300.0,
       "y": 0.517606489840492,
       "h_true": 0.5012993981216646,
       "u_requested": 0.6906902886089556,
       "u_applied": 0.6906902886089556,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 330.0,
       "y": 0.5140312156205462,
       "h_true": 0.5202621056370188,
       "u_requested": 0.6728401410598124,
       "u_applied": 0.6728401410598124,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 360.0,
       "y": 0.5362010077518039,
       "h_true": 0.533111893204824,
       "u_requested": 0.6523431099531574,
       "u_applied": 0.6523431099531574,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 390.0,
       "y": 0.5447940283597282,
       "h_true": 0.5405823591963175,
       "u_requested": 0.629294851229478,
       "u_applied": 0.629294851229478,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 420.0,
       "y": 0.5344806115079147,
       "h_true": 0.5431178805236299,
       "u_requested": 0.6113339410419452,
       "u_applied": 0.6113339410419452,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 450.0,
       "y": 0.5396760052151129,
       "h_true": 0.5421199725621395,
       "u_requested": 0.5881733784578359,
       "u_applied": 0.5881733784578359,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 480.0,
       "y": 0.5124827577894886,
       "h_true": 0.5380454199851408,
       "u_requested": 0.5742574643676595,
       "u_applied": 0.5742574643676595,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 510.0,
       "y": 0.5400769658347072,
       "h_true": 0.5320642067194151,
       "u_requested": 0.5620934888258659,
       "u_applied": 0.5620934888258659,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 540.0,
       "y": 0.5311754142054167,
       "h_true": 0.5255029909244255,
       "u_requested": 0.553294612337463,
       "u_applied": 0.553294612337463,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 570.0,
       "y": 0.5160942285998115,
       "h_true": 0.5187803689810753,
       "u_requested": 0.5447929684885464,
       "u_applied": 0.5447929684885464,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 600.0,
       "y": 0.5148333224680427,
       "h_true": 0.5122613321435203,
       "u_requested": 0.544649805188108,
       "u_applied": 0.544649805188108,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 630.0,
       "y": 0.49684016633596784,
       "h_true": 0.5066343911410028,
       "u_requested": 0.5453178198016544,
       "u_applied": 0.5453178198016544,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 660.0,
       "y": 0.48844117112193497,
       "h_true": 0.5019266587778262,
       "u_requested": 0.5446205615043809,
       "u_applied": 0.5446205615043809,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 690.0,
       "y": 0.5030718834207809,
       "h_true": 0.4982149126531919,
       "u_requested": 0.5464986663487077,
       "u_applied": 0.5464986663487077,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 720.0,
       "y": 0.48642337758942483,
       "h_true": 0.49546007993354396,
       "u_requested": 0.5505059391422269,
       "u_applied": 0.5505059391422269,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 750.0,
       "y": 0.4897577852344753,
       "h_true": 0.49366542747483516,
       "u_requested": 0.5527610794813645,
       "u_applied": 0.5527610794813645,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 780.0,
       "y": 0.4839324825290687,
       "h_true": 0.4926412109061569,
       "u_requested": 0.5538672512147659,
       "u_applied": 0.5538672512147659,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 810.0,
       "y": 0.47576249391380054,
       "h_true": 0.4922402683177362,
       "u_requested": 0.5612026791313041,
       "u_applied": 0.5612026791313041,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 840.0,
       "y": 0.4915855841447959,
       "h_true": 0.4924668891123761,
       "u_requested": 0.5622272800531931,
       "u_applied": 0.5622272800531931,
       "override": false,
       "reason": "ok"
      },
      {
       "t": 870.0,
       "y": 0.5041857981676985,
       "h_true": 0.49324342739288035,
       "u_requested": 0.5655536828889698,
       "u_applied": 0.5655536828889698,
       "override": false,
       "reason": "ok"
      }
     ],
     "dt": 1.0,
     "target": 0.5,
     "disturbance_at": 300.0,
     "meta": {
      "seed": 7,
      "scenario": 1001,
      "controller": "hw2-20261103-074537-698ba8-v2",
      "isolation": "docker",
      "disturbance": null,
      "duration_s": 900.0,
      "board_verification": {
       "label": "v2",
       "plant": "twin"
      },
      "synthetic": true
     }
    },
    "post_mae": 0.01788883810636398,
    "post_in_band": 1.0,
    "overrides": 0,
    "hard_violations": 0,
    "invalid_outputs": 0,
    "interlock_hit": false
   }
  ],
  "comparison": {
   "post_mae_v1": 0.12523299944439617,
   "post_mae_v2": 0.01788883810636398,
   "reduction": 0.857155556556747,
   "in_band_v1": 0.0,
   "in_band_v2": 1.0
  }
 },
 "prediction_vs_board": {
  "post_mae_v1": {
   "predicted": 0.12523299944439617,
   "measured": 0.12525345551775283
  },
  "post_mae_v2": {
   "predicted": 0.01788883810636398,
   "measured": 0.018275414896675272
  },
  "reduction": {
   "predicted": 0.857155556556747,
   "measured": 0.8540925292549314
  },
  "in_band_v1": {
   "predicted": 0.0,
   "measured": 0.0
  },
  "in_band_v2": {
   "predicted": 1.0,
   "measured": 1.0
  },
  "direction_agrees": true
 },
 "prediction_basis": "SYNTHETIC fixture built from hw2 twin-evaluation traces (not a board run)",
 "fake_board": true
};
