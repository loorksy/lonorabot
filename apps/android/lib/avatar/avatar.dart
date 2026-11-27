/// Lonora agent avatar: motion maths, widgets and studio catalogue.
library;

export 'src/avatar_colors.dart'
    show
        AvatarColor,
        avatarPalette,
        defaultAvatarColor,
        avatarHexColor,
        resolveAvatarColor,
        identityHash,
        seededRandom;
export 'src/avatar_faces.dart'
    show AvatarFace, avatarFaces, avatarFaceFor, avatarIsArabic;
export 'src/avatar_motion.dart' show AvatarMotion;
export 'src/avatar_state.dart'
    show
        LonoraAvatarState,
        AvatarVoice,
        avatarStateFor,
        activityPhaseAvatar,
        liveAvatarState;
export 'src/avatar_studio.dart' show AvatarStudioGrid;
export 'src/group_avatar.dart'
    show LonoraGroupAvatar, LonoraGroupAvatarLayout, LonoraAvatarMember;
export 'src/lonora_avatar.dart' show LonoraAvatar;
export 'src/motion.dart'
    show
        AvatarGeometry,
        AvatarMorph,
        AvatarBar,
        AvatarPersonality,
        FaceTokens,
        FacialGeometry,
        FaceReaction,
        MorphPlan,
        avatarFaceIds,
        avatarParticles,
        glyphScale,
        resolveAvatarFace,
        poseAt,
        planMorph,
        morphSegment,
        segmentPoints,
        avatarBarPoints,
        loopSeconds,
        posterPhase,
        stateGaze,
        avatarPersonality,
        faceReaction,
        idleAvatarPose,
        avatarTurn,
        faceTransform,
        parseHexColor;
